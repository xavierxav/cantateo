from django.contrib import admin
from django.db.models import Count

from ..models import Compositeur

@admin.register(Compositeur)
class CompositeurAdmin(admin.ModelAdmin):
    list_display = ('nom', 'get_partitions_count')
    search_fields = ('nom',)
    ordering = ('nom',)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            partitions_total=Count('partitions', distinct=True),
        )

    @admin.display(description='Partitions')
    def get_partitions_count(self, obj):
        return getattr(obj, 'partitions_total', obj.partitions.count())
