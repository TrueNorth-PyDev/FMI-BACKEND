from django.db import migrations, models
from decimal import Decimal
import django.core.validators

class Migration(migrations.Migration):

    dependencies = [
        ('investments', '0004_investment_opportunity_alter_investment_name_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='investment',
            name='current_value',
            field=models.DecimalField(decimal_places=2, help_text='Current valuation', max_digits=20, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))]),
        ),
        migrations.AlterField(
            model_name='investment',
            name='fund_size',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Total fund size (AUM)', max_digits=20, null=True),
        ),
        migrations.AlterField(
            model_name='investment',
            name='total_invested',
            field=models.DecimalField(decimal_places=2, help_text='Total amount invested', max_digits=20, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))]),
        ),
        migrations.AlterField(
            model_name='investment',
            name='unfunded_commitment',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Remaining capital commitment', max_digits=20, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))]),
        ),
    ]
