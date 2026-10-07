# Teaching edition: Configure Django admin separately from the React interface.
from django.contrib import admin

from apps.catalog.models import Category, Product, TaxRate, UnitOfMeasure

admin.site.register(Category)
admin.site.register(UnitOfMeasure)
admin.site.register(TaxRate)
admin.site.register(Product)
