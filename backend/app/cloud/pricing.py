"""Conservative public On-Demand estimates, never claims of realized savings."""
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from botocore.exceptions import BotoCoreError, ClientError
from botocore.config import Config


class EC2Pricing:
    def __init__(self, sdk):
        self.sdk = sdk
        self.cache = {}

    def quote(self, instance, region):
        # Do not price Spot, licensed/Marketplace images or dedicated placement as Linux On-Demand.
        if (instance.get('InstanceLifecycle') or instance.get('ProductCodes')
                or instance.get('Placement', {}).get('Tenancy') != 'default'
                or instance.get('PlatformDetails') not in ('Linux/UNIX', 'Windows')):
            return {'pricing_status': 'unsupported'}
        zone = instance.get('Placement', {}).get('AvailabilityZone')
        if zone and not re.fullmatch(re.escape(region) + '[a-z]', zone):
            return {'pricing_status': 'unsupported'}
        os_name = 'Linux' if instance['PlatformDetails'] == 'Linux/UNIX' else 'Windows'
        key = (region, instance['InstanceType'], os_name)
        if key not in self.cache:
            try:
                self.cache[key] = self.lookup(*key)
            except (BotoCoreError, ClientError, ValueError, KeyError, InvalidOperation):
                self.cache[key] = {'pricing_status': 'unavailable'}
        return dict(self.cache[key])

    def lookup(self, region, instance_type, os_name):
        filters = {'regionCode': region, 'instanceType': instance_type,
                   'operatingSystem': os_name, 'tenancy': 'Shared',
                   'preInstalledSw': 'NA', 'capacitystatus': 'Used',
                   'locationType': 'AWS Region'}
        client = self.sdk.client('pricing', region_name='us-east-1',
                                 config=Config(connect_timeout=5, read_timeout=15, retries={'max_attempts': 2, 'mode': 'standard'}))
        args = {'ServiceCode': 'AmazonEC2', 'MaxResults': 100,
                'Filters': [{'Type': 'TERM_MATCH', 'Field': k, 'Value': v} for k, v in filters.items()]}
        rates = set()
        while True:
            page = client.get_products(**args)
            for raw in page.get('PriceList', []):
                product = json.loads(raw)
                if product['product'].get('productFamily') != 'Compute Instance':
                    continue
                for term in product.get('terms', {}).get('OnDemand', {}).values():
                    for dim in term.get('priceDimensions', {}).values():
                        if dim.get('unit') == 'Hrs' and dim.get('beginRange') == '0' and dim.get('endRange') == 'Inf':
                            rate = Decimal(dim['pricePerUnit']['USD'])
                            if rate.is_finite() and rate > 0:
                                rates.add(rate)
            if not page.get('NextToken'):
                break
            args['NextToken'] = page['NextToken']
        if len(rates) != 1:
            return {'pricing_status': 'unavailable'}
        return {'pricing_status': 'available', 'on_demand_hourly_usd': str(rates.pop()),
                'pricing_source': 'AWS Price List Query API',
                'price_observed_at': datetime.now(timezone.utc).isoformat()}
