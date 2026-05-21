from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='barbearia',
            name='cpf_hash',
            field=models.CharField(blank=True, db_index=True, max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='barbearia',
            name='telefone_normalizado',
            field=models.CharField(blank=True, db_index=True, max_length=20, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='barbearia',
            name='email_verificado',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='barbearia',
            name='token_verificacao',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name='barbearia',
            name='token_expira',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
