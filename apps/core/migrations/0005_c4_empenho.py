from django.db import migrations, models
import django.db.models.deletion


def backfill_movimentacoes_iniciais(apps, schema_editor):
    """
    Para cada MovimentacaoEmpenho existente (antes eram ReforcoEmpenho):
      - preenche data com criado_em.date()
      - tipo já tem default 'REFORCO'

    Em seguida, para cada Empenho, cria uma MovimentacaoEmpenho com tipo=VALOR_INICIAL
    preservando o valor original antes de removê-lo.
    """
    Empenho = apps.get_model('core', 'Empenho')
    MovimentacaoEmpenho = apps.get_model('core', 'MovimentacaoEmpenho')

    # Preenche data das movimentações existentes (antigos reforços)
    for mov in MovimentacaoEmpenho.objects.all():
        if not mov.data:
            mov.data = mov.criado_em.date() if mov.criado_em else None
            mov.save(update_fields=['data'])

    # Cria VALOR_INICIAL para cada empenho
    for emp in Empenho.objects.all():
        if emp.valor is not None:
            MovimentacaoEmpenho.objects.create(
                empenho=emp,
                tipo='VALOR_INICIAL',
                valor=emp.valor,
                data=emp.criado_em.date() if emp.criado_em else None,
                descricao='Valor inicial (migrado do campo valor)',
            )


def reverse_backfill_movimentacoes(apps, schema_editor):
    MovimentacaoEmpenho = apps.get_model('core', 'MovimentacaoEmpenho')
    MovimentacaoEmpenho.objects.filter(tipo='VALOR_INICIAL').delete()


def backfill_empenho_empresa_fk(apps, schema_editor):
    Empenho = apps.get_model('core', 'Empenho')
    Empresa = apps.get_model('core', 'Empresa')

    for emp in Empenho.objects.all():
        if emp.empresa_nome:
            empresa_obj, _ = Empresa.objects.get_or_create(
                nome=emp.empresa_nome.strip(),
                defaults={'ativa': True},
            )
            emp.empresa_fk = empresa_obj
            emp.save(update_fields=['empresa_fk'])


def reverse_backfill_empresa(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    """
    C4: transforma NotaEmpenho → Empenho e ReforcoEmpenho → MovimentacaoEmpenho.

    Operações:
      - Renomeia models no estado Django (tabelas já têm nomes corretos desde Bloco B)
      - Adiciona tipo/data/observacao a MovimentacaoEmpenho
      - Backfill: data dos reforços existentes + cria VALOR_INICIAL por empenho
      - Adiciona empresa_fk (FK → Empresa) ao Empenho
      - Backfill empresa CharField → FK
      - Remove empresa CharField, renomeia empresa_fk → empresa
      - Adiciona modulo_origem ao Empenho
      - Remove campo valor do Empenho (preservado via VALOR_INICIAL em MovimentacaoEmpenho)
    """

    dependencies = [
        ('core', '0004_c3_status_requisicao'),
    ]

    operations = [

        # ── Renomear NotaEmpenho → Empenho (estado apenas, tabela já é core_empenho) ──
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RenameModel('NotaEmpenho', 'Empenho'),
            ],
            database_operations=[],
        ),

        # ── Renomear ReforcoEmpenho → MovimentacaoEmpenho (estado apenas) ──────────────
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RenameModel('ReforcoEmpenho', 'MovimentacaoEmpenho'),
            ],
            database_operations=[],
        ),

        # ── Novos campos em MovimentacaoEmpenho ───────────────────────────
        migrations.AddField(
            model_name='movimentacaoempenho',
            name='tipo',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('VALOR_INICIAL', 'Valor inicial'),
                    ('REFORCO', 'Reforço'),
                    ('ESTORNO', 'Estorno'),
                    ('ANULACAO', 'Anulação'),
                ],
                default='REFORCO',
                verbose_name='Tipo',
            ),
        ),
        migrations.AddField(
            model_name='movimentacaoempenho',
            name='data',
            field=models.DateField(
                null=True,
                blank=True,
                verbose_name='Data',
            ),
        ),
        migrations.AddField(
            model_name='movimentacaoempenho',
            name='observacao',
            field=models.TextField(blank=True, verbose_name='Observação'),
        ),

        # ── Backfill: data dos antigos reforços + criar VALOR_INICIAL ─────
        migrations.RunPython(backfill_movimentacoes_iniciais, reverse_backfill_movimentacoes),

        # ── Adicionar empresa_fk temporária ao Empenho ────────────────────
        # Usa campo auxiliar empresa_nome para ler o CharField antes de removê-lo
        migrations.RenameField(
            model_name='empenho',
            old_name='empresa',
            new_name='empresa_nome',
        ),
        migrations.AddField(
            model_name='empenho',
            name='empresa_fk',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='empenhos',
                to='core.empresa',
                verbose_name='Empresa',
            ),
        ),

        # ── Backfill empresa ──────────────────────────────────────────────
        migrations.RunPython(backfill_empenho_empresa_fk, reverse_backfill_empresa),

        # ── Remover CharField e renomear FK para nome final ───────────────
        migrations.RemoveField(model_name='empenho', name='empresa_nome'),
        migrations.RenameField(
            model_name='empenho',
            old_name='empresa_fk',
            new_name='empresa',
        ),

        # ── Adicionar modulo_origem ───────────────────────────────────────
        migrations.AddField(
            model_name='empenho',
            name='modulo_origem',
            field=models.CharField(
                max_length=20,
                default='REQUISICAO',
                verbose_name='Módulo de origem',
            ),
        ),

        # ── Remover campo valor (preservado em MovimentacaoEmpenho VALOR_INICIAL) ──
        migrations.RemoveField(model_name='empenho', name='valor'),
    ]
