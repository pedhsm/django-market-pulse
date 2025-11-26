from django.contrib import admin

# Register your models here.
from .models import Company,Article,MarketCandle

class ActiveCompanyFilter(admin.SimpleListFilter):
    title = "By active company"
    parameter_name = "active_company"

    def lookups(self, request, model_admin):
        qs = Company.objects.filter(is_active=True).order_by("name").only("id", "name", "ticker")
        return [(str(c.id), f"{c.name} | Ticker: {c.ticker}") for c in qs]

    def queryset(self, request, queryset):
        val = self.value()
        if val:
            return queryset.filter(company__id=val)
        return queryset
    
@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("id","name","ticker","is_active")
    search_fields = ("name","ticker")

@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("id","company","title","published","sentiment_label")
    list_filter  = (ActiveCompanyFilter, "sentiment_label", "source")            
    search_fields = ("company__ticker", "company__name", "title", "url")  
    list_select_related = ("company",)  
    ordering = ("-published",)     

@admin.register(MarketCandle)
class MarketAdmin(admin.ModelAdmin):
    list_display = ("id","company","ts","open","close","volume")
    list_filter = ("company",)
    date_hierarchy = "ts"
