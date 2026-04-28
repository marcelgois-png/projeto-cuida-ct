from django.db import migrations, models
import django.db.models.deletion


def backfill_empresa_fk(apps, schema_editor):
    Requisicao = apps.get_model('tracker', 'Requisicao')
    Empresa = apps.get_model('core', 'Empresa')
    empresa_map = {e.nome: e for e in Empresa.objects.all()}
    # Também tenta match case-insensitive
    empresa_map_lower = {nome.lower(): obj for nome, obj in empresa_map.items()}

    for req in Requisicao.objects.filter(empresa_nome__isnull=False).exclude(empresa_nome=''):
        empresa = empresa_map.get(req.empresa_nome) or empresa_map_lower.get(req.empresa_nome.lower())
        if empresa:
            req.empresa_fk = empresa
            req.save(update_fields=['empresa_fk'])


def reverse_backfill_empresa(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    """
    E0: Renomeia FKs legados em Requisicao e substitui empresa CharField por FK.

    - requisitante (FK → Solicitante)  →  solicitante
    - nota_empenho (FK → Empenho)      →  empenho
    - empresa (CharField)              →  empresa (FK → Empresa)
    """

    dependencies = [
        ('tracker', '0025_d2_visita_encaminhamento'),
        ('core', '0006_d1_lookup_models'),
    ]

    operations = [

        # ── Renomear FK requisitante → solicitante ────────────────────────
        migrations.RenameField(
            model_name='requisicao',
            old_name='requisitante',
            new_name='solicitante',
        ),

        # ── Renomear FK nota_empenho → empenho ────────────────────────────
        migrations.RenameField(
            model_name='requisicao',
            old_name='nota_empenho',
            new_name='empenho',
        ),

        # ── empresa CharField → FK ────────────────────────────────────────
        # 1. Renomear CharField para empresa_nome (campo temp para backfill)
        migrations.RenameField(
            model_name='requisicao',
            old_name='empresa',
            new_name='empresa_nome',
        ),

        # 2. Adicionar FK empresa_fk (nullable)
        migrations.AddField(
            model_name='requisicao',
            name='empresa_fk',
            field=models.ForeignKey(
                'core.Empresa',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
                related_name='requisicoes',
                verbose_name='Empresa',
            ),
        ),

        # 3. Backfill empresa_fk a partir de empresa_nome
        migrations.RunPython(backfill_empresa_fk, reverse_backfill_empresa),

        # 4. Remover campo temporário empresa_nome
        migrations.RemoveField(model_name='requisicao', name='empresa_nome'),

        # 5. Renomear empresa_fk → empresa
        migrations.RenameField(
            model_name='requisicao',
            old_name='empresa_fk',
            new_name='empresa',
        ),
    ]
