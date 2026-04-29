"""
Remove duplicate / invalid StatusRequisicao records:
  - ID 13: duplicate "12" entry
  - ID 19: "Deu merda" test entry

Both have 0 requisições linked (FK is SET_NULL), so deletion is safe.
"""

from django.db import migrations


def _delete_bad_statuses(apps, schema_editor):
    StatusRequisicao = apps.get_model("core", "StatusRequisicao")
    StatusRequisicao.objects.filter(pk__in=[13, 19]).delete()


def _noop(apps, schema_editor):
    pass  # no reverse: deleted data cannot be recreated automatically


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_d1_lookup_models"),
    ]

    operations = [
        migrations.RunPython(_delete_bad_statuses, _noop),
    ]
