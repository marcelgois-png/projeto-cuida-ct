from django.db import migrations


ACTIVE_STATUSES = {
    "01 CADASTRADA",
    "02 ENVIADA",
    "03 AGUARDANDO OS",
    "04 OS EMITIDA",
    "05 AGUARDANDO AVALIAÇÃO REQUISITANTE",
    "10 PENDENTE DE AUTORIZAÇÃO CHEFE UNIDADE",
}


def recalculate_execution_days(apps, schema_editor):
    Requisicao = apps.get_model("tracker", "Requisicao")

    for requisicao in Requisicao.objects.all().only(
        "id",
        "status_sipac",
        "data_cadastro",
        "data_execucao",
        "dias_para_execucao",
    ):
        status = (requisicao.status_sipac or "").strip()
        new_value = requisicao.dias_para_execucao

        if status == "06 FINALIZADA":
            if requisicao.data_cadastro and requisicao.data_execucao:
                new_value = max((requisicao.data_execucao - requisicao.data_cadastro).days, 0)
            else:
                new_value = None
        elif status not in ACTIVE_STATUSES:
            new_value = None
        else:
            continue

        if requisicao.dias_para_execucao != new_value:
            Requisicao.objects.filter(pk=requisicao.pk).update(dias_para_execucao=new_value)


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0007_alter_statussipacopcao_options_and_more"),
    ]

    operations = [
        migrations.RunPython(recalculate_execution_days, migrations.RunPython.noop),
    ]
