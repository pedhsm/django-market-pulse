from django.db import models

class Company(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=200)
    ticker = models.CharField(max_length=10,unique=True)
    is_active = models.BooleanField(default=True)

    class Meta():
        db_table = "companies" # Forcar o comportamento para nao renomear a tbl como "core_company"

    # A documentacao oficial do Django recomenda que haja essa funcao para facilitar o entendimento do retorno
    def __str__(self):
        return f"""Company: {self.name} | Ticker: {self.ticker}"""

class Article(models.Model):
    id = models.AutoField(primary_key=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name = "articles")
    title = models.CharField(max_length=300)
    url = models.URLField(unique=True)
    source = models.CharField(max_length=150)
    published = models.DateTimeField() # DataHora 
    ### PUXAR SENTIMENTO DAS NOTICIAS (CHECK) 
    sentiment_label = models.CharField(max_length=10,null=True, blank=True)
    sentiment_score = models.FloatField(null=True, blank=True)
    sentiment_model = models.CharField(max_length=80,null=True, blank=True)
    sentiment_lang = models.CharField(max_length=20,null=True, blank=True)
    sentiment_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "articles"
        indexes = [
            models.Index(fields=['company', '-published']),
            models.Index(fields=['-published']),
        ]

class MarketCandle(models.Model):
    id = models.AutoField(primary_key=True)
    company = models.ForeignKey(Company,on_delete=models.CASCADE,related_name = "marketdata")
    ts = models.DateTimeField() #DataHora
    open = models.DecimalField(max_digits=12, decimal_places=2)
    low = models.DecimalField(max_digits=12, decimal_places=2)
    high = models.DecimalField(max_digits=12, decimal_places=2)
    close = models.DecimalField(max_digits=12, decimal_places=2)
    volume = models.BigIntegerField()

    class Meta():
        db_table = "market_candle"
        indexes = [
            models.Index(fields=['company', 'ts']),   # busca por company + ts
            models.Index(fields=['-ts']),             # ordenação por ts desc
            ] 
        
        # Nao pode haver mais de um candlestick com mesmo momento para a mesma empresa
        constraints = [
            models.UniqueConstraint(fields=['company','ts'], name = 'unique_candle_company_ts')
            ]

