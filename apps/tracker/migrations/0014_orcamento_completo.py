import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0013_nota_empenho"),
    ]

    operations = [
        # Renomeia NotaEmpenho.numero → nota_empenho (o campo da migration 0013 se chamava 'numero')
        migrations.RenameField(
            model_name="notaempenho",
            old_name="numero",
            new_name="nota_empenho",
        ),
        # Remove o unique constraint do campo renomeado e mantém como simples CharField
        migrations.AlterField(
            model_name="notaempenho",
            name="nota_empenho",
            field=models.CharField(max_length=100, verbose_name="Nota de Empenho"),
        ),
        # Cria o modelo ReforcoEmpenho
        migrations.CreateModel(
            name="ReforcoEmpenho",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                (
                    "empenho",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reforcos",
                        to="tracker.notaempenho",
                        verbose_name="Nota de Empenho",
                    ),
                ),
                (
                    "valor",
                    models.DecimalField(decimal_places=2, max_digits=14, verbose_name="Valor do Reforço (R$)"),
                ),
                ("descricao", models.TextField(blank=True, verbose_name="Descrição")),
            ],
            options={
                "verbose_name": "Reforço de Empenho",
                "verbose_name_plural": "Reforços de Empenho",
                "ordering": ("-criado_em",),
            },
        ),
        # Adiciona orcamento_valor à Requisicao
        migrations.AddField(
            model_name="requisicao",
            name="orcamento_valor",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=12,
                null=True,
                verbose_name="Orçamento (R$)",
            ),
        ),
    ]
