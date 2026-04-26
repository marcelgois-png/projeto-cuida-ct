from django.db import migrations, models
import django.db.models.deletion


def backfill_setor_from_unidade_setor(apps, schema_editor):
    Solicitante = apps.get_model('core', 'Solicitante')
    Setor = apps.get_model('core', 'Setor')

    valores_unicos = (
        Solicitante.objects
        .exclude(unidade_setor='')
        .exclude(unidade_setor__isnull=True)
        .values_list('unidade_setor', flat=True)
        .distinct()
    )
    for nome in valores_unicos:
        Setor.objects.get_or_create(nome=nome.strip())

    for sol in Solicitante.objects.exclude(unidade_setor='').exclude(unidade_setor__isnull=True):
        try:
            setor = Setor.objects.get(nome=sol.unidade_setor.strip())
            sol.setor = setor
            sol.save(update_fields=['setor'])
        except Setor.DoesNotExist:
            pass


def reverse_backfill_setor(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    """
    C1: Cria Setor, renomeia Requisitante → Solicitante no estado Django
    (tabela já é core_solicitante desde o Bloco B), adiciona campos novos
    e faz backfill de setor a partir de unidade_setor.
    """

    dependencies = [
        ('core', '0001_initial'),
        # Garante que tracker/0021 rode antes do RenameModel abaixo,
        # para que o FK 'core.requisitante' exista no estado e seja
        # atualizado para 'core.Solicitante'.
        ('tracker', '0021_move_models_to_core'),
    ]

    operations = [

        # ── Criar model Setor ─────────────────────────────────────────────
        migrations.CreateModel(
            name='Setor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('nome', models.CharField(max_length=200, unique=True)),
                ('sigla', models.CharField(blank=True, max_length=20)),
                ('ativo', models.BooleanField(default=True)),
            ],
            options={'db_table': 'core_setor', 'ordering': ('nome',)},
        ),

        # ── Renomear Requisitante → Solicitante ──────────────────────────
        # db_table='core_solicitante' em ambos os lados → no-op no banco.
        # Usar RenameModel direto (não SeparateDatabaseAndState) para que
        # Django propague o rename às FKs de outros apps (ex: tracker).
        migrations.RenameModel('Requisitante', 'Solicitante'),

        # ── Novos campos em Solicitante ───────────────────────────────────
        migrations.AddField(
            model_name='solicitante',
            name='identificador',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='solicitante',
            name='tipo_identificador',
            field=models.CharField(
                blank=True,
                max_length=20,
                choices=[('SIAPE', 'SIAPE'), ('MATRICULA', 'Matrícula'), ('CPF', 'CPF')],
            ),
        ),
        migrations.AddField(
            model_name='solicitante',
            name='setor',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='solicitantes',
                to='core.setor',
            ),
        ),

        # ── Backfill: criar Setores e vincular Solicitantes ───────────────
        migrations.RunPython(backfill_setor_from_unidade_setor, reverse_backfill_setor),

        # ── Remover constraint antes de remover o campo ───────────────────
        # Sem isto, o Django tentaria recriar o índice sem unidade_setor,
        # falhando por chave_normalizada duplicada (mesmo solicitante em vários setores).
        migrations.RemoveConstraint(
            model_name='solicitante',
            name='tracker_unique_requisitante',
        ),

        # ── Remover campo unidade_setor ───────────────────────────────────
        migrations.RemoveField(model_name='solicitante', name='unidade_setor'),
    ]
