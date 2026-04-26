from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """
    C4 tracker side: atualiza explicitamente a FK nota_empenho de Requisicao para apontar
    para core.Empenho (após renomeação de NotaEmpenho → Empenho em core/0005).

    Apenas operação de estado — nenhuma DDL executada no banco.
    """

    dependencies = [
        ('tracker', '0023_c3_requisicao_status_fk'),
        ('core', '0005_c4_empenho'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='requisicao',
                    name='nota_empenho',
                    field=models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='requisicoes_empenho',
                        to='core.empenho',
                        verbose_name='Nota de Empenho',
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
