from django.db import migrations, models
import django.db.models.deletion


def backfill_taxonomia_para_3_models(apps, schema_editor):
    TaxonomiaServico = apps.get_model('core', 'TaxonomiaServico')
    DivisaoSINFRA = apps.get_model('core', 'DivisaoSINFRA')
    TipoServico = apps.get_model('core', 'TipoServico')
    Servico = apps.get_model('core', 'Servico')

    for taxa in TaxonomiaServico.objects.all():
        if not taxa.divisao:
            continue
        divisao, _ = DivisaoSINFRA.objects.get_or_create(nome=taxa.divisao.strip())
        tipo, _ = TipoServico.objects.get_or_create(
            nome=taxa.tipo_servico.strip() if taxa.tipo_servico else '',
            divisao=divisao,
        )
        if taxa.servico:
            Servico.objects.get_or_create(
                nome=taxa.servico.strip(),
                tipo_servico=tipo,
            )


def reverse_backfill(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    """
    C2 parte 1: cria DivisaoSINFRA, TipoServico, Servico e popula a partir de TaxonomiaServico.
    """

    dependencies = [
        ('core', '0002_c1_setor_solicitante'),
    ]

    operations = [

        # ── DivisaoSINFRA ─────────────────────────────────────────────────
        migrations.CreateModel(
            name='DivisaoSINFRA',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('nome', models.CharField(max_length=200, unique=True)),
                ('ativa', models.BooleanField(default=True)),
            ],
            options={'db_table': 'core_divisaosinfra', 'ordering': ('nome',)},
        ),

        # ── TipoServico ───────────────────────────────────────────────────
        migrations.CreateModel(
            name='TipoServico',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('nome', models.CharField(max_length=200)),
                ('divisao', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='tipos_servico',
                    to='core.divisaosinfra',
                    verbose_name='Divisão',
                )),
                ('ativo', models.BooleanField(default=True)),
            ],
            options={
                'db_table': 'core_tiposervico',
                'ordering': ('divisao__nome', 'nome'),
                'unique_together': {('divisao', 'nome')},
            },
        ),

        # ── Servico ───────────────────────────────────────────────────────
        migrations.CreateModel(
            name='Servico',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('nome', models.CharField(max_length=200)),
                ('tipo_servico', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='servicos',
                    to='core.tiposervico',
                    verbose_name='Tipo de serviço',
                )),
                ('ativo', models.BooleanField(default=True)),
            ],
            options={
                'db_table': 'core_servico',
                'ordering': ('tipo_servico__divisao__nome', 'tipo_servico__nome', 'nome'),
                'unique_together': {('tipo_servico', 'nome')},
            },
        ),

        # ── Backfill a partir de TaxonomiaServico ─────────────────────────
        migrations.RunPython(backfill_taxonomia_para_3_models, reverse_backfill),
    ]
