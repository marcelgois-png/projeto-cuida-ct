from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0015_backfill_orcamento_valor"),
    ]

    operations = [
        migrations.AddField(
            model_name="reforcoempenho",
            name="numero_processo_sipac",
            field=models.CharField(blank=True, max_length=100, verbose_name="Nº Processo SIPAC"),
        ),
    ]
