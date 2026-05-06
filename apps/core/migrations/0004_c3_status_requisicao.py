import re
import unicodedata

from django.db import migrations, models


def _rename_table(old, new):
    def _sql(schema_editor, src, dst):
        if schema_editor.connection.vendor == "mysql":
            schema_editor.execute(f"RENAME TABLE {src} TO {dst}")
        else:
            schema_editor.execute(f"ALTER TABLE {src} RENAME TO {dst}")

    return migrations.RunPython(
        lambda apps, se: _sql(se, old, new),
        lambda apps, se: _sql(se, new, old),
    )


_ACTIVE_CODES_NORMALIZED = {
    '01CADASTRADA',
    '02ENVIADA',
    '03AGUARDANDOOS',
    '04OSEMITIDA',
    '05AGUARDANDOAVALIACAOREQUISITANTE',
    '10PENDENTEDEAUTORIZACAOCHEFEUNIDADE',
}


def _norm(text):
    """Remove acentos, espaços e converte para maiúsculas — equivale a normalize_text do domain."""
    if not text:
        return ''
    text = unicodedata.normalize('NFKD', str(text))
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r'\s+', '', text).upper()


def backfill_mapeamento_situacao(apps, schema_editor):
    StatusRequisicao = apps.get_model('core', 'StatusRequisicao')
    # order_by('id') para não depender do Meta.ordering que ainda tem 'descricao'
    for status in StatusRequisicao.objects.order_by('id').all():
        situacao = 'ATIVA' if _norm(status.codigo) in _ACTIVE_CODES_NORMALIZED else 'INATIVA'
        status.mapeamento_situacao = situacao
        status.save(update_fields=['mapeamento_situacao'])


def reverse_backfill(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    """
    C3 parte 1: transforma StatusSipacOpcao → StatusRequisicao.

    Operações:
      - Renomeia model (estado) e tabela (DB): core_statussipacopcao → core_statusrequisicao
      - Renomeia campo descricao → codigo
      - Renomeia campo rotulo → nome
      - Adiciona campo mapeamento_situacao e faz backfill (ATIVA / INATIVA)
    """

    dependencies = [
        ('core', '0003_c2_servicos'),
    ]

    operations = [

        # ── Renomear model (estado) + tabela (banco) ──────────────────────
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RenameModel('StatusSipacOpcao', 'StatusRequisicao'),
                migrations.AlterModelTable(name='statusrequisicao', table='core_statusrequisicao'),
            ],
            database_operations=[
                _rename_table('core_statussipacopcao', 'core_statusrequisicao'),
            ],
        ),

        # ── Renomear campo descricao → codigo ─────────────────────────────
        migrations.RenameField(
            model_name='statusrequisicao',
            old_name='descricao',
            new_name='codigo',
        ),

        # ── Renomear campo rotulo → nome ──────────────────────────────────
        migrations.RenameField(
            model_name='statusrequisicao',
            old_name='rotulo',
            new_name='nome',
        ),

        # ── Adicionar mapeamento_situacao ─────────────────────────────────
        migrations.AddField(
            model_name='statusrequisicao',
            name='mapeamento_situacao',
            field=models.CharField(
                blank=True,
                max_length=20,
                choices=[('ATIVA', 'Ativa'), ('INATIVA', 'Inativa')],
                default='',
                verbose_name='Mapeamento situação',
            ),
            preserve_default=False,
        ),

        # ── Backfill mapeamento_situacao ──────────────────────────────────
        migrations.RunPython(backfill_mapeamento_situacao, reverse_backfill),
    ]
