from django.contrib.auth.models import Group,User  
from rest_framework import serializers
from core.models import Company,Article,MarketCandle

class CompanySerializer(serializers.HyperlinkedModelSerializer):
    class Meta():
        model = Company
        fields = ["id","name","ticker","is_active","url"]
        extra_kwargs = {
            'url' : {'view_name':'company-detail','lookup_field':'ticker'}
        }

class ArticleSerializer(serializers.HyperlinkedModelSerializer):
    api_url = serializers.HyperlinkedIdentityField(view_name="article-detail") 
    company = serializers.HyperlinkedRelatedField(view_name="company-detail", lookup_field="ticker", read_only=True)
    external_url = serializers.URLField(source="url", read_only=True)
    class Meta():
        model = Article
        fields = ["api_url","id","company","title","source","published","sentiment_label","external_url"]


class MarketCandleSerializer(serializers.HyperlinkedModelSerializer):
    company = serializers.HyperlinkedRelatedField(
        view_name = 'company-detail',
        lookup_field = 'ticker',
        read_only = True,
    )
    class Meta():
        model = MarketCandle
        fields = ["id","company","ts","open","high","low","close","volume","url"]
        extra_kwargs = {'url' : {'view_name':'marketcandle-detail'}}
