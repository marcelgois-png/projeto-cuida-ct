from django.core.management.base import BaseCommand, CommandError

from apps.tracker.importers import WorkbookImporter


class Command(BaseCommand):
    help = "Importa requisições CT-SINFRA a partir de arquivo XLSM/XLSX/CSV."

    def add_arguments(self, parser):
        parser.add_argument("arquivo", help="Caminho para o arquivo de importação.")

    def handle(self, *args, **options):
        caminho = options["arquivo"]
        try:
            with open(caminho, "rb") as file_handle:
                importacao = WorkbookImporter().import_file(file_handle)
        except FileNotFoundError as exc:
            raise CommandError(f"Arquivo não encontrado: {caminho}") from exc
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Importação concluída: {importacao.nome_arquivo} ({importacao.resumo_json.get('total_processado', 0)} registros)."
            )
        )
