from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """
    Bloco B: remove 9 models do estado Django do tracker.

    Nenhuma operação de banco é executada — as tabelas já foram
    renomeadas por core/0001_initial. Aqui apenas:
      1. Atualiza as FKs de Requisicao para apontar para core.*
      2. Remove os models do estado Django do tracker
    """

    dependencies = [
        ('tracker', '0020_alter_encaminhamentodiretor_requisicoes_and_more'),
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[

                # ── 1. Atualizar FKs antes de deletar os models de origem ──
                migrations.AlterField(
                    model_name='requisicao',
                    name='predio',
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='requisicoes',
                        to='core.predio',
                    ),
                ),
                migrations.AlterField(
                    model_name='requisicao',
                    name='requisitante',
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='requisicoes',
                        to='core.requisitante',
                    ),
                ),
                migrations.AlterField(
                    model_name='requisicao',
                    name='taxonomia',
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='requisicoes',
                        to='core.taxonomiaservico',
                    ),
                ),
                migrations.AlterField(
                    model_name='requisicao',
                    name='nota_empenho',
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='requisicoes_empenho',
                        to='core.notaempenho',
                        verbose_name='Nota de Empenho',
                    ),
                ),

                # ── 2. Remover models do estado Django do tracker ──────────
                migrations.DeleteModel(name='ReforcoEmpenho'),
                migrations.DeleteModel(name='NotaEmpenho'),
                migrations.DeleteModel(name='TaxonomiaServico'),
                migrations.DeleteModel(name='StatusSipacOpcao'),
                migrations.DeleteModel(name='GUTParametro'),
                migrations.DeleteModel(name='RegraPrioridade'),
                migrations.DeleteModel(name='Empresa'),
                migrations.DeleteModel(name='Predio'),
                migrations.DeleteModel(name='Requisitante'),

            ],
            database_operations=[
                # Sem operações de banco — tabelas já renomeadas em core/0001_initial
            ],
        ),
    ]
