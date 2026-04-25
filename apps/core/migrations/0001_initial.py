from django.db import migrations, models
import django.db.models.deletion


PRIORITY_CHOICES = [
    ('1 - Urgente', '1 - Urgente'),
    ('2 - Alta', '2 - Alta'),
    ('3 - Média', '3 - Média'),
    ('4 - Baixa', '4 - Baixa'),
    ('5 - Analisar', '5 - Analisar'),
    ('6 - Inativa', '6 - Inativa'),
]


class Migration(migrations.Migration):
    """
    Bloco B: move 9 models do tracker para o core via SeparateDatabaseAndState.

    state_operations  — atualiza o Django ORM state (nenhuma query DDL)
    database_operations — renomeia as tabelas no banco (sem DROP/CREATE)

    Ordem das tabelas:
      tracker_predio           → core_predio
      tracker_requisitante     → core_solicitante
      tracker_taxonomiaservico → core_taxonomiaservico
      tracker_statussipacopcao → core_statussipacopcao
      tracker_gutparametro     → core_gutparametro
      tracker_regraprioridade  → core_regraprioridade
      tracker_empresa          → core_empresa
      tracker_notaempenho      → core_empenho
      tracker_reforcoempenho   → core_movimentacaoempenho
    """

    initial = True

    dependencies = [
        ('tracker', '0020_alter_encaminhamentodiretor_requisicoes_and_more'),
    ]

    operations = [

        # ── Predio ────────────────────────────────────────────────────────
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='Predio',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('criado_em', models.DateTimeField(auto_now_add=True)),
                        ('atualizado_em', models.DateTimeField(auto_now=True)),
                        ('nome', models.CharField(max_length=255, unique=True)),
                        ('chave_normalizada', models.CharField(editable=False, max_length=255, unique=True)),
                        ('latitude', models.DecimalField(blank=True, decimal_places=6, max_digits=10, null=True)),
                        ('longitude', models.DecimalField(blank=True, decimal_places=6, max_digits=10, null=True)),
                        ('visivel_publicamente', models.BooleanField(default=True)),
                    ],
                    options={'ordering': ('nome',), 'db_table': 'core_predio'},
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql='RENAME TABLE tracker_predio TO core_predio',
                    reverse_sql='RENAME TABLE core_predio TO tracker_predio',
                ),
            ],
        ),

        # ── Requisitante (tabela renomeada para core_solicitante) ─────────
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='Requisitante',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('criado_em', models.DateTimeField(auto_now_add=True)),
                        ('atualizado_em', models.DateTimeField(auto_now=True)),
                        ('nome', models.CharField(max_length=255)),
                        ('chave_normalizada', models.CharField(editable=False, max_length=255)),
                        ('unidade_setor', models.CharField(blank=True, max_length=255)),
                        ('contato_url', models.CharField(blank=True, max_length=30)),
                        ('visivel_publicamente', models.BooleanField(default=True)),
                    ],
                    options={
                        'ordering': ('nome',),
                        'db_table': 'core_solicitante',
                        'constraints': [
                            models.UniqueConstraint(
                                fields=('chave_normalizada', 'unidade_setor'),
                                name='tracker_unique_requisitante',
                            )
                        ],
                    },
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql='RENAME TABLE tracker_requisitante TO core_solicitante',
                    reverse_sql='RENAME TABLE core_solicitante TO tracker_requisitante',
                ),
            ],
        ),

        # ── TaxonomiaServico ──────────────────────────────────────────────
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='TaxonomiaServico',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('criado_em', models.DateTimeField(auto_now_add=True)),
                        ('atualizado_em', models.DateTimeField(auto_now=True)),
                        ('divisao', models.CharField(max_length=255)),
                        ('tipo_servico', models.CharField(max_length=255)),
                        ('servico', models.CharField(blank=True, max_length=255)),
                        ('chave_normalizada', models.CharField(editable=False, max_length=255, unique=True)),
                        ('ordem_divisao', models.PositiveIntegerField(blank=True, null=True)),
                        ('ordem_tipo', models.PositiveIntegerField(blank=True, null=True)),
                        ('ordem_servico', models.PositiveIntegerField(blank=True, null=True)),
                    ],
                    options={'ordering': ('divisao', 'tipo_servico', 'servico'), 'db_table': 'core_taxonomiaservico'},
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql='RENAME TABLE tracker_taxonomiaservico TO core_taxonomiaservico',
                    reverse_sql='RENAME TABLE core_taxonomiaservico TO tracker_taxonomiaservico',
                ),
            ],
        ),

        # ── StatusSipacOpcao ──────────────────────────────────────────────
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='StatusSipacOpcao',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('criado_em', models.DateTimeField(auto_now_add=True)),
                        ('atualizado_em', models.DateTimeField(auto_now=True)),
                        ('numero', models.CharField(blank=True, max_length=2)),
                        ('rotulo', models.CharField(blank=True, max_length=255)),
                        ('descricao', models.CharField(max_length=255, unique=True)),
                        ('chave_normalizada', models.CharField(editable=False, max_length=255, unique=True)),
                        ('ordem', models.PositiveIntegerField(blank=True, null=True)),
                        ('ativa', models.BooleanField(default=True)),
                    ],
                    options={'ordering': ('ordem', 'numero', 'descricao'), 'db_table': 'core_statussipacopcao'},
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql='RENAME TABLE tracker_statussipacopcao TO core_statussipacopcao',
                    reverse_sql='RENAME TABLE core_statussipacopcao TO tracker_statussipacopcao',
                ),
            ],
        ),

        # ── GUTParametro ──────────────────────────────────────────────────
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='GUTParametro',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('criado_em', models.DateTimeField(auto_now_add=True)),
                        ('atualizado_em', models.DateTimeField(auto_now=True)),
                        ('tipo', models.CharField(
                            choices=[('GRAVIDADE', 'Gravidade'), ('URGENCIA', 'Urgência'), ('TENDENCIA', 'Tendência')],
                            max_length=20,
                        )),
                        ('valor', models.PositiveSmallIntegerField()),
                        ('descricao', models.CharField(max_length=255)),
                    ],
                    options={
                        'verbose_name': 'Parâmetro GUT',
                        'verbose_name_plural': 'Parâmetros GUT',
                        'ordering': ('tipo', '-valor'),
                        'db_table': 'core_gutparametro',
                        'unique_together': {('tipo', 'valor')},
                    },
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql='RENAME TABLE tracker_gutparametro TO core_gutparametro',
                    reverse_sql='RENAME TABLE core_gutparametro TO tracker_gutparametro',
                ),
            ],
        ),

        # ── RegraPrioridade ───────────────────────────────────────────────
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='RegraPrioridade',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('criado_em', models.DateTimeField(auto_now_add=True)),
                        ('atualizado_em', models.DateTimeField(auto_now=True)),
                        ('chave_normalizada', models.CharField(max_length=255, unique=True)),
                        ('prioridade', models.CharField(choices=PRIORITY_CHOICES, max_length=30)),
                        ('descricao', models.CharField(blank=True, max_length=255)),
                        ('origem', models.CharField(default='planilha', max_length=50)),
                        ('ativa', models.BooleanField(default=True)),
                    ],
                    options={'ordering': ('prioridade', 'chave_normalizada'), 'db_table': 'core_regraprioridade'},
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql='RENAME TABLE tracker_regraprioridade TO core_regraprioridade',
                    reverse_sql='RENAME TABLE core_regraprioridade TO tracker_regraprioridade',
                ),
            ],
        ),

        # ── Empresa ───────────────────────────────────────────────────────
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='Empresa',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('criado_em', models.DateTimeField(auto_now_add=True)),
                        ('atualizado_em', models.DateTimeField(auto_now=True)),
                        ('nome', models.CharField(max_length=255, unique=True)),
                        ('ativa', models.BooleanField(default=True)),
                    ],
                    options={
                        'verbose_name': 'Empresa',
                        'verbose_name_plural': 'Empresas',
                        'ordering': ('nome',),
                        'db_table': 'core_empresa',
                    },
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql='RENAME TABLE tracker_empresa TO core_empresa',
                    reverse_sql='RENAME TABLE core_empresa TO tracker_empresa',
                ),
            ],
        ),

        # ── NotaEmpenho (tabela renomeada para core_empenho) ──────────────
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='NotaEmpenho',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('criado_em', models.DateTimeField(auto_now_add=True)),
                        ('atualizado_em', models.DateTimeField(auto_now=True)),
                        ('nota_empenho', models.CharField(max_length=100, verbose_name='Nota de Empenho')),
                        ('valor', models.DecimalField(decimal_places=2, max_digits=14, verbose_name='Valor (R$)')),
                        ('numero_processo_sipac', models.CharField(blank=True, max_length=100, verbose_name='Nº Processo SIPAC')),
                        ('link_processo_sipac', models.URLField(blank=True, max_length=1000, verbose_name='Link Processo SIPAC')),
                        ('empresa', models.CharField(blank=True, max_length=255, verbose_name='Empresa')),
                    ],
                    options={
                        'verbose_name': 'Nota de Empenho',
                        'verbose_name_plural': 'Notas de Empenho',
                        'ordering': ('-criado_em',),
                        'db_table': 'core_empenho',
                    },
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql='RENAME TABLE tracker_notaempenho TO core_empenho',
                    reverse_sql='RENAME TABLE core_empenho TO tracker_notaempenho',
                ),
            ],
        ),

        # ── ReforcoEmpenho (tabela renomeada para core_movimentacaoempenho)
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='ReforcoEmpenho',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('criado_em', models.DateTimeField(auto_now_add=True)),
                        ('atualizado_em', models.DateTimeField(auto_now=True)),
                        ('empenho', models.ForeignKey(
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name='reforcos',
                            to='core.notaempenho',
                            verbose_name='Nota de Empenho',
                        )),
                        ('valor', models.DecimalField(decimal_places=2, max_digits=14, verbose_name='Valor do Reforço (R$)')),
                        ('numero_processo_sipac', models.CharField(blank=True, max_length=100, verbose_name='Nº Processo SIPAC')),
                        ('descricao', models.TextField(blank=True, verbose_name='Descrição')),
                    ],
                    options={
                        'verbose_name': 'Reforço de Empenho',
                        'verbose_name_plural': 'Reforços de Empenho',
                        'ordering': ('-criado_em',),
                        'db_table': 'core_movimentacaoempenho',
                    },
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql='RENAME TABLE tracker_reforcoempenho TO core_movimentacaoempenho',
                    reverse_sql='RENAME TABLE core_movimentacaoempenho TO tracker_reforcoempenho',
                ),
            ],
        ),

    ]
