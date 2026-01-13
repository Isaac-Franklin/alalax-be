import ssl
import certifi
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

# Allowed cities in Canada
ALLOWED_CITIES = ['calgary', 'airdrie', 'chestermere', 'okotoks']



class DeliveryFeeCalculator:
    def __init__(self):
        # Create SSL context
        ctx = ssl.create_default_context(cafile=certifi.where())
        
        # Initialize geolocator with SSL context
        self.geolocator = Nominatim(
            user_agent="alalax_delivery_calculator",
            ssl_context=ctx
        )
        
        # Define pricing tiers (per km)
        self.pricing_tiers = [
            {'max_km': 5, 'rate': Decimal('0.00')},  # First 5km free
            {'max_km': float('inf'), 'rate': Decimal('0.90')},  # $0.90/km after 5km
        ]
        
        # Base fees by weight
        self.base_fees = {
            'small': Decimal('7.99'),   # 1-5kg
            'medium': Decimal('11.99'),  # 5-15kg
            'large': Decimal('17.99'),   # 15-30kg
        }
        
        # Speed fees
        self.speed_fees = {
            'standard': Decimal('0.00'),
            'express': Decimal('4.99'),
            'instant': Decimal('6.99')
        }
        
        # Addon fees
        self.addon_prices = {
            'signature_confirmation': Decimal('1.50'),
            'fragile_handling': Decimal('2.50'),
            'oversized_package': Decimal('8.00')
        }
    
    def validate_location(self, address):
        """Validates that the address is within allowed cities"""
        address_lower = address.lower()
        city_found = any(city in address_lower for city in ALLOWED_CITIES)
        
        if not city_found:
            return False, None, f"Delivery only available in: {', '.join(ALLOWED_CITIES).title()}"
        
        if 'canada' not in address_lower and 'ab' not in address_lower:
            address = f"{address}, Alberta, Canada"
        
        return True, address, None
    

    def calculate_distance(self, pickup_address, delivery_address):
        """Calculate estimated driving distance between two addresses"""
        # TEMPORARY: Use fixed distance for testing
        logger.warning("Using mock distance - SSL certificate issue")
        return 10.0, None  # Mock 10km distance
        
        # Original code below (comment out for now)
        # geolocator = Nominatim(user_agent="alalax_delivery_calculator")
        # ... rest of code

    # def calculate_distance(self, pickup_address, delivery_address):
    #     """Calculate estimated driving distance between two addresses"""
    #     try:
    #         # Use the initialized geolocator with SSL context
    #         pickup_loc = self.geolocator.geocode(pickup_address)
    #         delivery_loc = self.geolocator.geocode(delivery_address)
            
    #         if not pickup_loc or not delivery_loc:
    #             return None, "Could not find one or both addresses"
            
    #         pickup_coords = (pickup_loc.latitude, pickup_loc.longitude)
    #         delivery_coords = (delivery_loc.latitude, delivery_loc.longitude)
    #         straight_distance = geodesic(pickup_coords, delivery_coords).kilometers
            
    #         # Apply 1.4x multiplier to estimate driving distance
    #         estimated_driving_distance = straight_distance * 1.4
            
    #         return round(estimated_driving_distance, 2), None
            
    #     except Exception as e:
    #         logger.error(f"Distance calculation error: {str(e)}")
    #         return None, f"Error calculating distance: {str(e)}"
    
    def calculate_delivery_fee(self, distance_km, package_weight, delivery_speed, addons):
        """Calculate total delivery fee based on all parameters"""
        fee_breakdown = {
            'base_fee': Decimal('0.00'),
            'distance_fee': Decimal('0.00'),
            'speed_fee': Decimal('0.00'),
            'addons_fee': Decimal('0.00'),
            'total_fee': Decimal('0.00')
        }
        
        def get_weight_range(weight):
            if weight == "1-5kg":
                return 5,
            elif weight == "5-15kg":
                return 15
            elif weight == "15-30kg":
                return 30
            else:
                return 35

        
        # 1. BASE FEE - Based on package weight
        print('package_weight')
        print(package_weight)
        if get_weight_range(package_weight) <= 5:
            fee_breakdown['base_fee'] = self.base_fees['small']
        elif get_weight_range(package_weight) <= 15:
            fee_breakdown['base_fee'] = self.base_fees['medium']
        elif get_weight_range(package_weight) <= 30:
            fee_breakdown['base_fee'] = self.base_fees['large']
        else:
            fee_breakdown['base_fee'] = self.base_fees['large']
        
        # 2. DISTANCE FEE - First 5km free, then $0.90 per km
        if distance_km > 5:
            extra_km = distance_km - 5
            fee_breakdown['distance_fee'] = Decimal(str(extra_km)) * Decimal('0.90')
        
        # 3. SPEED FEE
        fee_breakdown['speed_fee'] = self.speed_fees.get(delivery_speed.lower(), Decimal('0.00'))
        
        # 4. ADDONS FEE
        addons_total = Decimal('0.00')
        applied_addons = []
        
        for addon in addons:
            addon_key = addon.lower().replace(' ', '_')
            if addon_key in self.addon_prices:
                addons_total += self.addon_prices[addon_key]
                applied_addons.append(addon)
        
        # Automatically add oversized addon if weight > 30kg
        if get_weight_range(package_weight) > 30 and 'oversized_package' not in [a.lower().replace(' ', '_') for a in addons]:
            addons_total += self.addon_prices['oversized_package']
            applied_addons.append('oversized_package')
        
        fee_breakdown['addons_fee'] = addons_total
        fee_breakdown['applied_addons'] = applied_addons
        
        # Calculate total
        fee_breakdown['total_fee'] = (
            fee_breakdown['base_fee'] + 
            fee_breakdown['distance_fee'] + 
            fee_breakdown['speed_fee'] + 
            fee_breakdown['addons_fee']
        )
        
        # Round all decimals to 2 places
        for key in fee_breakdown:
            if isinstance(fee_breakdown[key], Decimal):
                fee_breakdown[key] = round(fee_breakdown[key], 2)
        
        return fee_breakdown
    
    def get_delivery_quote(self, pickup_address, delivery_address, package_weight, delivery_speed, addons):
        """Get complete delivery quote"""
        # Validate locations
        is_valid, cleaned_pickup, error = self.validate_location(pickup_address)
        if not is_valid:
            return {'success': False, 'error': f'Pickup location error: {error}'}
        
        is_valid, cleaned_delivery, error = self.validate_location(delivery_address)
        if not is_valid:
            return {'success': False, 'error': f'Delivery location error: {error}'}
        
        # Calculate distance
        distance_km, distance_error = self.calculate_distance(cleaned_pickup, cleaned_delivery)
        if distance_error:
            return {'success': False, 'error': distance_error}
        
        # Calculate fees
        fee_breakdown = self.calculate_delivery_fee(
            distance_km=distance_km,
            package_weight=package_weight,
            delivery_speed=delivery_speed,
            addons=addons
        )
        
        # Determine estimated delivery time
        delivery_times = {
            'standard': '3-6 hours',
            'express': '1-2 hours',
            'instant': 'Less than 1 hour'
        }
        
        return {
            'success': True,
            'quote': {
                'total_fee': float(fee_breakdown['total_fee']),
                'currency': 'CAD',
                'breakdown': {
                    'base_fee': float(fee_breakdown['base_fee']),
                    'distance_fee': float(fee_breakdown['distance_fee']),
                    'speed_fee': float(fee_breakdown['speed_fee']),
                    'addons_fee': float(fee_breakdown['addons_fee'])
                },
                'details': {
                    'distance_km': distance_km,
                    'package_weight_kg': package_weight,
                    'delivery_speed': delivery_speed,
                    'estimated_delivery_time': delivery_times.get(delivery_speed.lower()),
                    'applied_addons': fee_breakdown.get('applied_addons', [])
                }
            }
        }
        
        
        
        


















