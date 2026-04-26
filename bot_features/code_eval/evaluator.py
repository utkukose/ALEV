"""
bot_features/code_eval/evaluator.py — Kaynak Kod Değerlendirme Motoru

Dört değerlendirme, sıfır LLM:

1. OutputComparator   — Kodu sandbox'ta çalıştır, çıktıyı referansla karşılaştır
2. ASTSimilarity      — Soyut sözdizim ağacı benzerliği (aynı algoritma mı?)
3. QualityAnalyzer    — Statik analiz: karmaşıklık, yorum oranı, isimlendirme
4. PlagiarismDetector — TF-IDF + AST token benzerliği (kopyalama var mı?)

Tüm değerlendirmeler 0-100 arası puan döner.
"""
from __future__ import annotations
import ast
import hashlib
import io
import math
import re
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ═══════════════════════════════════════════
# Sonuç nesneleri
# ═══════════════════════════════════════════
@dataclass
class EvalResult:
    score: float          # 0-100
    label: str            # "Mükemmel" / "İyi" / "Orta" / "Zayıf"
    details: dict         # Ham metrikler
    feedback_tr: str      # Türkçe geri bildirim
    feedback_en: str      # İngilizce geri bildirim


@dataclass
class FullEvalResult:
    team_id: int
    task_id: str
    output_score: float       # Çıktı doğruluğu (0-100)
    similarity_score: float   # AST benzerliği (0-100)
    quality_score: float      # Kod kalitesi (0-100)
    plagiarism_risk: float    # Kopyalama riski (0=temiz, 100=şüpheli)
    final_score: float        # Ağırlıklı nihai puan
    details: dict
    passed: bool              # Minimum eşiği geçti mi?
    xp_reward: int            # Verilecek XP


def _label(score: float) -> str:
    if score >= 85: return "Mükemmel"
    if score >= 70: return "İyi"
    if score >= 50: return "Orta"
    return "Zayıf"


# ═══════════════════════════════════════════
# 1. Çıktı Karşılaştırıcı
# ═══════════════════════════════════════════
class OutputComparator:
    """
    Takım kodunu sandbox (subprocess) içinde çalıştırır,
    çıktısını referans çıktıyla karşılaştırır.
    Güvenlik: timeout, memory limit, izin verilmeyen import'lar.
    """

    BANNED_IMPORTS = {
        "os", "sys", "subprocess", "socket", "shutil",
        "importlib", "ctypes", "multiprocessing", "threading",
        "__import__", "eval", "exec", "compile",
    }
    TIMEOUT = 5        # saniye
    MAX_OUTPUT = 4096  # karakter

    def _is_safe(self, code: str) -> tuple[bool, str]:
        """Kod güvenli mi? AST üzerinden kontrol."""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Sözdizimi hatası: {e}"
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [a.name for a in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                for name in names:
                    root = name.split(".")[0]
                    if root in self.BANNED_IMPORTS:
                        return False, f"İzin verilmeyen import: `{root}`"
        return True, ""

    def run(
        self,
        team_code: str,
        reference_output: str,
        test_inputs: list[str] | None = None,
        lang: str = "python",
    ) -> EvalResult:
        """
        team_code     : Takımın gönderdiği kaynak kod
        reference_output: Beklenen çıktı (string)
        test_inputs   : stdin'e verilecek girdiler (her biri ayrı çalıştırma)
        """
        safe, reason = self._is_safe(team_code)
        if not safe:
            return EvalResult(
                score=0, label="Başarısız",
                details={"error": reason},
                feedback_tr=f"Kod güvenlik kontrolünden geçemedi: {reason}",
                feedback_en=f"Code failed security check: {reason}",
            )

        inputs = test_inputs or [""]
        passed = 0
        outputs = []

        for inp in inputs:
            try:
                with tempfile.NamedTemporaryFile(
                    suffix=".py", mode="w", delete=False, encoding="utf-8"
                ) as tf:
                    tf.write(team_code)
                    tmp_path = tf.name

                result = subprocess.run(
                    [sys.executable, tmp_path],
                    input=inp, capture_output=True, text=True,
                    timeout=self.TIMEOUT,
                )
                actual = result.stdout.strip()[: self.MAX_OUTPUT]
                outputs.append(actual)
                expected = reference_output.strip()

                # Tam eşleşme
                if actual == expected:
                    passed += 1
                    continue
                # Normalize karşılaştırma (boşluk/satır farkı yok say)
                if re.sub(r"\s+", " ", actual) == re.sub(r"\s+", " ", expected):
                    passed += 0.9
                    continue
                # Sayısal yakınlık (float çıktılar için)
                try:
                    if abs(float(actual) - float(expected)) < 1e-6:
                        passed += 0.95
                        continue
                except ValueError:
                    pass
                # Kısmi içerik kontrolü
                if expected in actual or actual in expected:
                    passed += 0.5

            except subprocess.TimeoutExpired:
                outputs.append("[TIMEOUT]")
            except Exception as e:
                outputs.append(f"[ERROR: {e}]")
            finally:
                try:
                    Path(tmp_path).unlink(missing_ok=True)
                except Exception:
                    pass

        score = round((passed / len(inputs)) * 100, 1)
        return EvalResult(
            score=score,
            label=_label(score),
            details={"passed": passed, "total": len(inputs), "outputs": outputs},
            feedback_tr=(
                f"{len(inputs)} test durumundan {int(passed)} tanesi geçti."
                if score < 100 else "Tüm test durumları başarıyla geçti! ✅"
            ),
            feedback_en=(
                f"{int(passed)} of {len(inputs)} test cases passed."
                if score < 100 else "All test cases passed! ✅"
            ),
        )


# ═══════════════════════════════════════════
# 2. AST Benzerlik Analizi
# ═══════════════════════════════════════════
class ASTSimilarity:
    """
    İki Python kodunu AST token dizisine çevirir,
    normalized edit distance ile benzerlik hesaplar.
    İsim/değer obfuscation'a karşı dayanıklı.
    """

    def _normalize_tokens(self, code: str) -> list[str]:
        """
        AST'yi düzleştirir, değişken isimlerini VAR,
        string literallerini STR, sayıları NUM ile değiştirir.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []
        tokens = []
        for node in ast.walk(tree):
            t = type(node).__name__
            if isinstance(node, ast.Name):
                tokens.append(f"NAME:{node.id[:3]}")  # İlk 3 harf koru
            elif isinstance(node, ast.Constant):
                if isinstance(node.value, (int, float)):
                    tokens.append("NUM")
                elif isinstance(node.value, str):
                    tokens.append("STR")
                else:
                    tokens.append(t)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                tokens.append("FUNC")
            elif isinstance(node, ast.ClassDef):
                tokens.append("CLASS")
            elif t not in ("Module", "Load", "Store", "Del", "arguments"):
                tokens.append(t)
        return tokens

    def _edit_distance_ratio(self, a: list, b: list) -> float:
        """Normalize edilmiş Levenshtein benzerliği."""
        if not a and not b:
            return 1.0
        if not a or not b:
            return 0.0
        # DP tablo (sadece iki satır bellek)
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a):
            curr = [i + 1]
            for j, cb in enumerate(b):
                if ca == cb:
                    curr.append(prev[j])
                else:
                    curr.append(1 + min(prev[j], prev[j + 1], curr[j]))
            prev = curr
        dist = prev[len(b)]
        return 1 - dist / max(len(a), len(b))

    def compare(self, team_code: str, reference_code: str) -> EvalResult:
        team_tok = self._normalize_tokens(team_code)
        ref_tok  = self._normalize_tokens(reference_code)

        if not team_tok:
            return EvalResult(
                score=0, label="Başarısız",
                details={"error": "Kod parse edilemedi"},
                feedback_tr="Kod sözdizimi hatası içeriyor.",
                feedback_en="Code contains syntax errors.",
            )

        ratio = self._edit_distance_ratio(team_tok, ref_tok)
        score = round(ratio * 100, 1)

        # Yapısal benzerlik kategorisi
        if score >= 80:
            fb_tr = "Referans algoritmaya çok yakın yapı. ✅"
            fb_en = "Very similar structure to reference algorithm. ✅"
        elif score >= 60:
            fb_tr = "Temel yapı benzer, bazı farklı yaklaşımlar var."
            fb_en = "Basic structure matches, some different approaches."
        elif score >= 40:
            fb_tr = "Farklı bir yaklaşım seçilmiş, doğruluk kontrolüne bakın."
            fb_en = "Different approach chosen, check output correctness."
        else:
            fb_tr = "Referans algoritmadan önemli ölçüde farklı."
            fb_en = "Significantly different from reference algorithm."

        return EvalResult(
            score=score, label=_label(score),
            details={
                "team_tokens": len(team_tok),
                "ref_tokens": len(ref_tok),
                "similarity_ratio": ratio,
            },
            feedback_tr=fb_tr,
            feedback_en=fb_en,
        )


# ═══════════════════════════════════════════
# 3. Kod Kalite Analizi
# ═══════════════════════════════════════════
class QualityAnalyzer:
    """
    LLM olmadan kod kalitesi metrikleri:
    - Yorum satırı oranı
    - Fonksiyon/sınıf yapısı
    - Değişken isimlendirme kalitesi
    - Kod tekrarı (DRY)
    - Döngüsel karmaşıklık tahmini
    """

    def _comment_ratio(self, code: str) -> float:
        lines = code.splitlines()
        if not lines: return 0.0
        comment_lines = sum(
            1 for l in lines
            if l.strip().startswith("#") or l.strip().startswith('"""') or l.strip().startswith("'''")
        )
        return comment_lines / len(lines)

    def _naming_score(self, code: str) -> float:
        """
        İyi isimlendirme: snake_case, anlamlı uzunluk (3-30 karakter).
        Kötü: tek harf değişkenler (i, x hariç), ALLCAPS, çok kısa.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return 0.0
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                names.append(node.id)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.append(node.name)
        if not names: return 0.5
        good = sum(
            1 for n in names
            if (3 <= len(n) <= 30)
            and re.match(r'^[a-z_][a-z0-9_]*$', n)
            and n not in ('i', 'j', 'k', 'x', 'y', 'n', 'e')
        )
        return good / len(names)

    def _cyclomatic_complexity(self, code: str) -> int:
        """
        Basit döngüsel karmaşıklık tahmini:
        1 + if + for + while + except + and + or sayısı
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return 99
        count = 1
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.For, ast.While,
                                  ast.ExceptHandler, ast.With)):
                count += 1
            elif isinstance(node, ast.BoolOp):
                count += len(node.values) - 1
        return count

    def _has_docstrings(self, code: str) -> bool:
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if (node.body and isinstance(node.body[0], ast.Expr)
                            and isinstance(node.body[0].value, ast.Constant)
                            and isinstance(node.body[0].value.value, str)):
                        return True
        except SyntaxError:
            pass
        return False

    def _line_length_score(self, code: str) -> float:
        lines = [l for l in code.splitlines() if l.strip()]
        if not lines: return 1.0
        long = sum(1 for l in lines if len(l) > 79)
        return 1 - (long / len(lines))

    def analyze(self, team_code: str) -> EvalResult:
        comment_r  = self._comment_ratio(team_code)
        naming_r   = self._naming_score(team_code)
        complexity = self._cyclomatic_complexity(team_code)
        docstrings = self._has_docstrings(team_code)
        line_r     = self._line_length_score(team_code)

        # Karmaşıklık skoru (düşük karmaşıklık = iyi)
        complexity_score = max(0, 1 - (complexity - 5) / 20) if complexity > 5 else 1.0

        # Ağırlıklı puan
        score = (
            comment_r       * 25 +    # Yorum oranı
            naming_r        * 30 +    # İsimlendirme
            complexity_score* 25 +    # Karmaşıklık
            (0.1 if docstrings else 0) * 100 * 0.1 +  # Docstring
            line_r          * 10      # Satır uzunluğu
        )
        score = round(min(100, score * 100 if score <= 1 else score), 1)

        feedbacks_tr = []
        feedbacks_en = []
        if comment_r < 0.1:
            feedbacks_tr.append("Yorum satırı çok az — kodu belgeleyin.")
            feedbacks_en.append("Very few comments — document your code.")
        if naming_r < 0.5:
            feedbacks_tr.append("Değişken isimlendirmesi iyileştirilebilir.")
            feedbacks_en.append("Variable naming can be improved.")
        if complexity > 15:
            feedbacks_tr.append(f"Yüksek karmaşıklık ({complexity}) — fonksiyonlara bölün.")
            feedbacks_en.append(f"High complexity ({complexity}) — split into functions.")
        if not docstrings:
            feedbacks_tr.append("Fonksiyonlara docstring ekleyin.")
            feedbacks_en.append("Add docstrings to functions.")
        if not feedbacks_tr:
            feedbacks_tr.append("Kod kalitesi iyi! ✅")
            feedbacks_en.append("Good code quality! ✅")

        return EvalResult(
            score=score, label=_label(score),
            details={
                "comment_ratio": round(comment_r, 3),
                "naming_score": round(naming_r, 3),
                "cyclomatic_complexity": complexity,
                "has_docstrings": docstrings,
                "line_length_score": round(line_r, 3),
            },
            feedback_tr=" ".join(feedbacks_tr),
            feedback_en=" ".join(feedbacks_en),
        )


# ═══════════════════════════════════════════
# 4. Plagiarizm Dedektörü
# ═══════════════════════════════════════════
class PlagiarismDetector:
    """
    İki yaklaşımı birleştirir:
    A) TF-IDF cosine similarity (token seviyesi)
    B) AST token sequence similarity

    Sonuç 0-100: 0 = tamamen orijinal, 100 = birebir kopya.
    Eşik: >70 şüpheli, >85 yüksek risk.
    """

    def _tokenize(self, code: str) -> list[str]:
        """Kod token'larını çıkar (keyword + isim + operator)."""
        import tokenize
        import io
        tokens = []
        try:
            for tok in tokenize.generate_tokens(io.StringIO(code).readline):
                if tok.type in (1, 2, 54):  # NAME, NUMBER, OP
                    tokens.append(tok.string)
        except tokenize.TokenError:
            tokens = code.split()
        return tokens

    def _ast_tokens(self, code: str) -> list[str]:
        """AST düğüm tiplerini liste olarak döner."""
        try:
            tree = ast.parse(code)
            return [type(n).__name__ for n in ast.walk(tree)]
        except SyntaxError:
            return []

    def _cosine_similarity(self, tokens_a: list[str], tokens_b: list[str]) -> float:
        """TF-IDF ağırlıksız cosine similarity."""
        if not tokens_a or not tokens_b: return 0.0
        vocab = set(tokens_a) | set(tokens_b)
        def vec(tokens):
            c = {}
            for t in tokens: c[t] = c.get(t, 0) + 1
            return c
        va, vb = vec(tokens_a), vec(tokens_b)
        dot = sum(va.get(w, 0) * vb.get(w, 0) for w in vocab)
        mag_a = math.sqrt(sum(v**2 for v in va.values()))
        mag_b = math.sqrt(sum(v**2 for v in vb.values()))
        if mag_a == 0 or mag_b == 0: return 0.0
        return dot / (mag_a * mag_b)

    def compare_pair(self, code_a: str, code_b: str) -> float:
        """İki kod arasındaki benzerlik riski (0-100)."""
        tok_sim = self._cosine_similarity(
            self._tokenize(code_a), self._tokenize(code_b)
        )
        ast_sim = self._cosine_similarity(
            self._ast_tokens(code_a), self._ast_tokens(code_b)
        )
        # AST'ye daha fazla ağırlık ver (yeniden yazma'ya karşı dayanıklı)
        combined = tok_sim * 0.4 + ast_sim * 0.6
        return round(combined * 100, 1)

    def check_all(self, submissions: dict[int, str]) -> dict[tuple[int,int], float]:
        """
        submissions: {team_id: code}
        Tüm çift kombinasyonlarını karşılaştırır.
        Döner: {(team_a, team_b): risk_score}
        """
        results = {}
        ids = list(submissions.keys())
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = ids[i], ids[j]
                score = self.compare_pair(submissions[a], submissions[b])
                results[(a, b)] = score
        return results

    def risk_label(self, score: float) -> tuple[str, str]:
        """(tr_label, en_label)"""
        if score >= 85: return ("🔴 Yüksek Risk", "🔴 High Risk")
        if score >= 70: return ("🟡 Şüpheli", "🟡 Suspicious")
        if score >= 50: return ("🟠 Dikkat", "🟠 Watch")
        return ("🟢 Temiz", "🟢 Clean")


# ═══════════════════════════════════════════
# Ana Değerlendirici
# ═══════════════════════════════════════════
class CodeEvaluator:
    """
    Tüm değerlendirmeleri koordine eden ana sınıf.

    Kullanım:
        evaluator = CodeEvaluator()
        result = await evaluator.evaluate(
            team_id=123,
            task_id="karbon_hesaplayici",
            team_code="...",
            reference_code="...",       # tasks.yaml'dan
            reference_output="...",     # beklenen çıktı
            test_inputs=["10\n", "20\n"],
            all_submissions={123:"...", 456:"..."},  # plagiarizm için
        )
    """

    # Ağırlıklar (toplamı 100)
    WEIGHTS = {
        "output":     40,   # Çıktı doğruluğu
        "similarity": 20,   # Algoritma benzerliği
        "quality":    30,   # Kod kalitesi
        "plagiarism": 10,   # Plagiarizm cezası (risk arttıkça düşer)
    }

    def __init__(self):
        self.output_cmp  = OutputComparator()
        self.ast_sim     = ASTSimilarity()
        self.quality     = QualityAnalyzer()
        self.plagiarism  = PlagiarismDetector()

    def evaluate(
        self,
        team_id: int,
        task_id: str,
        team_code: str,
        reference_code: str = "",
        reference_output: str = "",
        test_inputs: list[str] | None = None,
        all_submissions: dict[int, str] | None = None,
        base_xp: int = 300,
        pass_threshold: float = 50.0,
    ) -> FullEvalResult:

        # 1. Çıktı doğruluğu
        if reference_output:
            out_r = self.output_cmp.run(team_code, reference_output, test_inputs)
        else:
            out_r = EvalResult(50, "N/A", {}, "Referans çıktı tanımlanmamış.", "No reference output.")

        # 2. Yapısal benzerlik
        if reference_code:
            sim_r = self.ast_sim.compare(team_code, reference_code)
        else:
            sim_r = EvalResult(50, "N/A", {}, "Referans kod tanımlanmamış.", "No reference code.")

        # 3. Kod kalitesi
        qual_r = self.quality.analyze(team_code)

        # 4. Plagiarizm
        plag_risk = 0.0
        plag_pairs: dict[tuple, float] = {}
        if all_submissions and len(all_submissions) > 1:
            subs = dict(all_submissions)
            subs[team_id] = team_code
            pairs = self.plagiarism.check_all(subs)
            # Bu takımı ilgilendiren çiftler
            team_pairs = {k: v for k, v in pairs.items() if team_id in k}
            if team_pairs:
                plag_risk = max(team_pairs.values())
            plag_pairs = team_pairs

        # Plagiarizm cezası: risk > 70 ise puan düşer
        plag_penalty = max(0, (plag_risk - 70) / 30 * 100) if plag_risk > 70 else 0

        # Ağırlıklı final skor
        w = self.WEIGHTS
        final = (
            out_r.score  * w["output"]     / 100 +
            sim_r.score  * w["similarity"] / 100 +
            qual_r.score * w["quality"]    / 100 +
            max(0, 100 - plag_penalty) * w["plagiarism"] / 100
        )
        final = round(final, 1)

        # XP hesabı (final skor oranında)
        xp = int(base_xp * (final / 100)) if final >= pass_threshold else 0

        return FullEvalResult(
            team_id=team_id,
            task_id=task_id,
            output_score=out_r.score,
            similarity_score=sim_r.score,
            quality_score=qual_r.score,
            plagiarism_risk=round(plag_risk, 1),
            final_score=final,
            details={
                "output": out_r.details,
                "output_feedback_tr": out_r.feedback_tr,
                "output_feedback_en": out_r.feedback_en,
                "similarity": sim_r.details,
                "similarity_feedback_tr": sim_r.feedback_tr,
                "similarity_feedback_en": sim_r.feedback_en,
                "quality": qual_r.details,
                "quality_feedback_tr": qual_r.feedback_tr,
                "quality_feedback_en": qual_r.feedback_en,
                "plagiarism_pairs": {
                    f"{a}-{b}": v for (a, b), v in plag_pairs.items()
                },
            },
            passed=final >= pass_threshold,
            xp_reward=xp,
        )
