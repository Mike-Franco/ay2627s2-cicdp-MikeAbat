# TORY-56 follow-up: a product's category must belong to the product's business,
# enforced by the database as well as by Product.clean(). Kept separate from
# 0011, which was already merged and may be applied on existing databases.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogue', '0011_product_categories'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='category',
            constraint=models.UniqueConstraint(fields=('id', 'business'), name='category_id_business_key'),
        ),
        migrations.RunSQL(
            """
            ALTER TABLE catalogue_product ADD CONSTRAINT product_category_business_fk
            FOREIGN KEY (category_id, business_id) REFERENCES catalogue_category (id, business_id)
            """,
            "ALTER TABLE catalogue_product DROP CONSTRAINT product_category_business_fk",
        ),
    ]
