import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0012_empresa"),
    ]

    operations = [
        migrations.CreateModel(
            name="NotaEmpenho",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("numero", models.CharField(max_length=100, unique=True, verbose_name="Nota de Empenho")),
                ("valor", models.DecimalField(decimal_places=2, max_digits=14, verbose_name="Valor (R$)")),
                ("numero_processo_sipac", models.CharField(blank=True, max_length=100, verbose_name="Nº Processo SIPAC")),
                ("link_processo_sipac", models.URLField(blank=True, max_length=1000, verbose_name="Link Processo SIPAC")),
                ("empresa", models.CharField(blank=True, max_length=255, verbose_name="Empresa")),
            ],
            options={
                "verbose_name": "Nota de Empenho",
                "verbose_name_plural": "Notas de Empenho",
                "ordering": ("-criado_em",),
            },
        ),
        migrations.AddField(
            model_name="requisicao",
            name="nota_empenho",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="requisicoes_empenho",
                to="tracker.notaempenho",
                verbose_name="Nota de Empenho",
            ),
        ),
    ]
