import re
import unicodedata

from django.db import migrations, models
import django.db.models.deletion


def _norm(text):
    """Remove acentos, espaços e converte para maiúsculas."""
    if not text:
        return ''
    text = unicodedata.normalize('NFKD', str(text))
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r'\s+', '', text).upper()


def backfill_status_sipac_fk(apps, schema_editor):
    Requisicao = apps.get_model('tracker', 'Requisicao')
    StatusRequisicao = apps.get_model('core', 'StatusRequisicao')

    status_map = {_norm(s.codigo): s for s in StatusRequisicao.objects.order_by('id').all()}

    sem_match = []
    for req in Requisicao.objects.all():
        if not req.status_sipac:
            continue
        key = _norm(req.status_sipac)
        status = status_map.get(key)
        if status:
            req.status_sipac_fk = status
            req.save(update_fields=['status_sipac_fk'])
        else:
            sem_match.append(f'{req.numero}: {req.status_sipac!r}')

    if sem_match:
        print(f'AVISO C3: {len(sem_match)} requisições sem status correspondente:')
        for info in sem_match[:20]:
            print(f'  {info}')


def reverse_backfill(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    """
    C3 parte 2: em Requisicao, adiciona FK status_sipac_fk → StatusRequisicao,
    faz backfill do CharField antigo, remove CharField, renomeia FK.

    O FK permanece nullable permanentemente (nem toda requisição tem status SIPAC conhecida).
    """

    dependencies = [
        ('tracker', '0022_c2_requisicao_servicos'),
        ('core', '0004_c3_status_requisicao'),
    ]

    operations = [

        # ── Adicionar FK temporária ───────────────────────────────────────
        migrations.AddField(
            model_name='requisicao',
            name='status_sipac_fk',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='requisicoes',
                to='core.statusrequisicao',
                verbose_name='Status SIPAC',
            ),
        ),

        # ── Backfill ──────────────────────────────────────────────────────
        migrations.RunPython(backfill_status_sipac_fk, reverse_backfill),

        # ── Remover CharField antigo ──────────────────────────────────────
        migrations.RemoveField(model_name='requisicao', name='status_sipac'),

        # ── Renomear FK para nome final ───────────────────────────────────
        migrations.RenameField(
            model_name='requisicao',
            old_name='status_sipac_fk',
            new_name='status_sipac',
        ),
    ]
