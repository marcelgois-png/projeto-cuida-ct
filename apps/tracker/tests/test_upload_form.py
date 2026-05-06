from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.tracker.forms import ImportacaoForm, _TAMANHO_MAXIMO_BYTES

_ZIP_MAGIC = b"PK\x03\x04"
_XLSX_CONTENT = _ZIP_MAGIC + b"\x00" * 100


def _upload(nome, conteudo, content_type="application/octet-stream"):
    return SimpleUploadedFile(nome, conteudo, content_type=content_type)


class ImportacaoFormExtensaoTests(TestCase):
    def test_xlsx_valido(self):
        form = ImportacaoForm(files={"arquivo": _upload("planilha.xlsx", _XLSX_CONTENT)})
        self.assertTrue(form.is_valid(), form.errors)

    def test_xlsm_valido(self):
        form = ImportacaoForm(files={"arquivo": _upload("planilha.xlsm", _XLSX_CONTENT)})
        self.assertTrue(form.is_valid(), form.errors)

    def test_csv_valido(self):
        csv_content = b"codigo,assunto\n001,Reparo\n"
        form = ImportacaoForm(files={"arquivo": _upload("dados.csv", csv_content, "text/csv")})
        self.assertTrue(form.is_valid(), form.errors)

    def test_pdf_invalido(self):
        form = ImportacaoForm(files={"arquivo": _upload("doc.pdf", b"%PDF-1.4")})
        self.assertFalse(form.is_valid())
        self.assertIn("arquivo", form.errors)
        self.assertIn(".pdf", form.errors["arquivo"][0])

    def test_sem_extensao_invalido(self):
        form = ImportacaoForm(files={"arquivo": _upload("semextensao", b"conteudo")})
        self.assertFalse(form.is_valid())

    def test_extensao_case_insensitive(self):
        form = ImportacaoForm(files={"arquivo": _upload("PLANILHA.XLSX", _XLSX_CONTENT)})
        self.assertTrue(form.is_valid(), form.errors)


class ImportacaoFormTamanhoTests(TestCase):
    def test_arquivo_dentro_do_limite(self):
        conteudo = _ZIP_MAGIC + b"\x00" * (5 * 1024 * 1024)
        form = ImportacaoForm(files={"arquivo": _upload("ok.xlsx", conteudo)})
        self.assertTrue(form.is_valid(), form.errors)

    def test_arquivo_no_limite_exato(self):
        conteudo = _ZIP_MAGIC + b"\x00" * (_TAMANHO_MAXIMO_BYTES - 4)
        form = ImportacaoForm(files={"arquivo": _upload("limite.xlsx", conteudo)})
        self.assertTrue(form.is_valid(), form.errors)

    def test_arquivo_acima_do_limite_invalido(self):
        conteudo = _ZIP_MAGIC + b"\x00" * _TAMANHO_MAXIMO_BYTES
        form = ImportacaoForm(files={"arquivo": _upload("grande.xlsx", conteudo)})
        self.assertFalse(form.is_valid())
        self.assertIn("Limite", form.errors["arquivo"][0])


class ImportacaoFormMagicBytesTests(TestCase):
    def test_xlsx_com_magic_valido(self):
        form = ImportacaoForm(files={"arquivo": _upload("ok.xlsx", _XLSX_CONTENT)})
        self.assertTrue(form.is_valid(), form.errors)

    def test_xlsx_sem_magic_invalido(self):
        form = ImportacaoForm(files={"arquivo": _upload("falso.xlsx", b"NOTAZIP!!")})
        self.assertFalse(form.is_valid())
        self.assertIn("válido", form.errors["arquivo"][0])

    def test_csv_nao_verifica_magic(self):
        form = ImportacaoForm(files={"arquivo": _upload("dados.csv", b"codigo,assunto\n")})
        self.assertTrue(form.is_valid(), form.errors)

    def test_xlsm_com_magic_valido(self):
        form = ImportacaoForm(files={"arquivo": _upload("macro.xlsm", _XLSX_CONTENT)})
        self.assertTrue(form.is_valid(), form.errors)
