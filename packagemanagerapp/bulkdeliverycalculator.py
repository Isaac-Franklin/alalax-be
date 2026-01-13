import ssl
import certifi
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

ALLOWED_CITIES = ['calgary', 'airdrie', 'chestermere', 'okotoks']


def get_weight_range(weight):
    """
    Convert weight string to numeric value
    
    Args:
        weight (str): Weight range string (e.g., '1-5kg', '5-15kg')
    
    Returns:
        int: Maximum weight in kg for the range
    """
    if weight == "1-5kg":
        return 5
    elif weight == "5-15kg":
        return 15
    elif weight == "15-30kg":
        return 30
    else:
        return 35


class BulkDeliveryFeeCalculator:
    """
    Calculator for bulk shipment pricing with discounted rates.
    
    Bulk pricing offers discounts compared to single shipment pricing:
    - Small (1-5kg): $5.99 (vs $7.99 single)
    - Medium (5-15kg): $9.99 (vs $11.99 single)
    - Large (15-30kg): $15.99 (vs $17.99 single)
    """
    
    def __init__(self):
        """Initialize the bulk delivery fee calculator with pricing structure"""
        # Create SSL context for secure geocoding
        ctx = ssl.create_default_context(cafile=certifi.where())
        
        # Initialize geolocator with SSL context
        self.geolocator = Nominatim(
            user_agent="alalax_bulk_delivery_calculator",
            ssl_context=ctx
        )
        
        # Distance pricing tiers (per km)
        self.pricing_tiers = [
            {'max_km': 5, 'rate': Decimal('0.00')},  # First 5km free
            {'max_km': float('inf'), 'rate': Decimal('0.90')},  # $0.90/km after 5km
        ]
        
        # BULK PRICING - Discounted base fees by weight
        self.base_fees = {
            'small': Decimal('5.99'),   # 1-5kg (was 7.99 for single)
            'medium': Decimal('9.99'),  # 5-15kg (was 11.99 for single)
            'large': Decimal('15.99'),   # 15-30kg (was 17.99 for single)
        }
        
        # Speed fees (same as single shipment)
        self.speed_fees = {
            'standard': Decimal('0.00'),
            'express': Decimal('4.99'),
            'instant': Decimal('6.99')
        }
        
        # Addon fees (same as single shipment)
        self.addon_prices = {
            'signature_confirmation': Decimal('1.50'),
            'fragile_handling': Decimal('2.50'),
            'oversized_package': Decimal('8.00')
        }
        
        # Allowed cities for delivery
        self.allowed_cities = ALLOWED_CITIES
    
    def validate_location(self, address):
        """
        Validates that the address is within allowed cities
        
        Args:
            address (str): Address to validate
        
        Returns:
            tuple: (is_valid: bool, cleaned_address: str|None, error: str|None)
        """
        if not address:
            return False, None, "Address is required"
        
        address_lower = address.lower()
        
        # Check if address contains any allowed city
        city_found = any(city in address_lower for city in self.allowed_cities)
        
        if not city_found:
            allowed_cities_str = ', '.join(city.title() for city in self.allowed_cities)
            return False, None, f"Delivery only available in: {allowed_cities_str}"
        
        # Ensure province and country are included for better geocoding
        if 'canada' not in address_lower and 'ab' not in address_lower:
            address = f"{address}, Alberta, Canada"
        
        return True, address, None
    
    def calculate_distance(self, pickup_address, delivery_address):
        """
        Calculate estimated driving distance between two addresses
        
        Args:
            pickup_address (str): Pickup location address
            delivery_address (str): Delivery location address
        
        Returns:
            tuple: (distance_km: float|None, error: str|None)
        """
        # TEMPORARY: Use fixed distance for testing SSL certificate issue
        logger.warning("Using mock distance - SSL certificate issue")
        return 10.0, None  # Mock 10km distance
        
        # TODO: Uncomment and use actual distance calculation once SSL is configured
        # try:
        #     # Geocode both addresses
        #     pickup_loc = self.geolocator.geocode(pickup_address)
        #     delivery_loc = self.geolocator.geocode(delivery_address)
        #     
        #     if not pickup_loc:
        #         return None, f"Could not find pickup address: {pickup_address}"
        #     
        #     if not delivery_loc:
        #         return None, f"Could not find delivery address: {delivery_address}"
        #     
        #     # Get coordinates
        #     pickup_coords = (pickup_loc.latitude, pickup_loc.longitude)
        #     delivery_coords = (delivery_loc.latitude, delivery_loc.longitude)
        #     
        #     # Calculate straight-line distance
        #     straight_distance = geodesic(pickup_coords, delivery_coords).kilometers
        #     
        #     # Apply 1.4x multiplier to estimate driving distance
        #     estimated_driving_distance = straight_distance * 1.4
        #     
        #     return round(estimated_driving_distance, 2), None
        #     
        # except Exception as e:
        #     logger.error(f"Distance calculation error: {str(e)}")
        #     return None, f"Error calculating distance: {str(e)}"
    
    def calculate_delivery_fee(self, distance_km, package_weight, delivery_speed, addons=None):
        """
        Calculate total delivery fee based on all parameters
        
        Args:
            distance_km (float): Distance in kilometers
            package_weight (str): Weight range (e.g., '1-5kg', '5-15kg')
            delivery_speed (str): Delivery speed ('standard', 'express', 'instant')
            addons (list): List of addon names (optional)
        
        Returns:
            dict: Fee breakdown with keys:
                - base_fee (Decimal)
                - distance_fee (Decimal)
                - speed_fee (Decimal)
                - addons_fee (Decimal)
                - total_fee (Decimal)
                - applied_addons (list)
        """
        if addons is None:
            addons = []
        
        # Initialize fee breakdown
        fee_breakdown = {
            'base_fee': Decimal('0.00'),
            'distance_fee': Decimal('0.00'),
            'speed_fee': Decimal('0.00'),
            'addons_fee': Decimal('0.00'),
            'total_fee': Decimal('0.00'),
            'applied_addons': []
        }
        
        # Get numeric weight value
        weight_kg = get_weight_range(package_weight)
        
        # 1. BASE FEE - Based on package weight (BULK PRICING)
        if weight_kg <= 5:
            fee_breakdown['base_fee'] = self.base_fees['small']
        elif weight_kg <= 15:
            fee_breakdown['base_fee'] = self.base_fees['medium']
        elif weight_kg <= 30:
            fee_breakdown['base_fee'] = self.base_fees['large']
        else:
            # For oversized packages, use large base fee
            fee_breakdown['base_fee'] = self.base_fees['large']
        
        # 2. DISTANCE FEE - First 5km free, then $0.90 per km
        if distance_km > 5:
            extra_km = distance_km - 5
            fee_breakdown['distance_fee'] = Decimal(str(extra_km)) * Decimal('0.90')
        
        # 3. SPEED FEE - Based on delivery speed
        speed_key = delivery_speed.lower() if delivery_speed else 'standard'
        fee_breakdown['speed_fee'] = self.speed_fees.get(speed_key, Decimal('0.00'))
        
        # 4. ADDONS FEE - Calculate total for all addons
        addons_total = Decimal('0.00')
        applied_addons = []
        
        # Process requested addons
        for addon in addons:
            addon_key = addon.lower().replace(' ', '_')
            if addon_key in self.addon_prices:
                addons_total += self.addon_prices[addon_key]
                applied_addons.append(addon)
        
        # Automatically add oversized addon if weight > 30kg
        if weight_kg > 30 and 'oversized_package' not in [a.lower().replace(' ', '_') for a in addons]:
            addons_total += self.addon_prices['oversized_package']
            applied_addons.append('oversized_package')
        
        fee_breakdown['addons_fee'] = addons_total
        fee_breakdown['applied_addons'] = applied_addons
        
        # 5. CALCULATE TOTAL FEE
        fee_breakdown['total_fee'] = (
            fee_breakdown['base_fee'] + 
            fee_breakdown['distance_fee'] + 
            fee_breakdown['speed_fee'] + 
            fee_breakdown['addons_fee']
        )
        
        # Round all decimal values to 2 places
        for key in fee_breakdown:
            if isinstance(fee_breakdown[key], Decimal):
                fee_breakdown[key] = round(fee_breakdown[key], 2)
        
        return fee_breakdown
    
    def get_delivery_quote(self, pickup_address, delivery_address, package_weight, delivery_speed, addons=None):
        """
        Get complete delivery quote with validation and fee calculation
        
        Args:
            pickup_address (str): Pickup location address
            delivery_address (str): Delivery location address
            package_weight (str): Weight range (e.g., '1-5kg')
            delivery_speed (str): Delivery speed ('standard', 'express', 'instant')
            addons (list): List of addon names (optional)
        
        Returns:
            dict: Complete quote with structure:
                - success (bool)
                - quote (dict) or error (str)
        """
        if addons is None:
            addons = []
        
        # Validate pickup location
        is_valid, cleaned_pickup, error = self.validate_location(pickup_address)
        if not is_valid:
            return {
                'success': False,
                'error': f'Pickup location error: {error}'
            }
        
        # Validate delivery location
        is_valid, cleaned_delivery, error = self.validate_location(delivery_address)
        if not is_valid:
            return {
                'success': False,
                'error': f'Delivery location error: {error}'
            }
        
        # Calculate distance
        distance_km, distance_error = self.calculate_distance(cleaned_pickup, cleaned_delivery)
        if distance_error:
            return {
                'success': False,
                'error': distance_error
            }
        
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
        
        # Return complete quote
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
                    'package_weight': package_weight,
                    'delivery_speed': delivery_speed,
                    'estimated_delivery_time': delivery_times.get(delivery_speed.lower(), '3-6 hours'),
                    'applied_addons': fee_breakdown.get('applied_addons', [])
                }
            }
        }
    
    def validate_package_weight(self, package_weight):
        """
        Validate package weight format
        
        Args:
            package_weight (str): Weight range string
        
        Returns:
            tuple: (is_valid: bool, error: str|None)
        """
        valid_weights = ['1-5kg', '5-15kg', '15-30kg', '30kg+']
        
        if package_weight not in valid_weights:
            return False, f"Invalid package weight. Must be one of: {', '.join(valid_weights)}"
        
        return True, None
    
    def validate_delivery_speed(self, delivery_speed):
        """
        Validate delivery speed option
        
        Args:
            delivery_speed (str): Delivery speed option
        
        Returns:
            tuple: (is_valid: bool, error: str|None)
        """
        valid_speeds = ['standard', 'express', 'instant']
        
        speed_lower = delivery_speed.lower() if delivery_speed else ''
        
        if speed_lower not in valid_speeds:
            return False, f"Invalid delivery speed. Must be one of: {', '.join(valid_speeds)}"
        
        return True, None
    
    def get_pricing_info(self):
        """
        Get information about bulk pricing structure
        
        Returns:
            dict: Pricing information
        """
        return {
            'base_fees': {
                'small_1_5kg': float(self.base_fees['small']),
                'medium_5_15kg': float(self.base_fees['medium']),
                'large_15_30kg': float(self.base_fees['large'])
            },
            'distance_pricing': {
                'first_5km': 'Free',
                'per_km_after_5km': '0.90 CAD'
            },
            'speed_fees': {
                'standard': float(self.speed_fees['standard']),
                'express': float(self.speed_fees['express']),
                'instant': float(self.speed_fees['instant'])
            },
            'addon_fees': {
                'signature_confirmation': float(self.addon_prices['signature_confirmation']),
                'fragile_handling': float(self.addon_prices['fragile_handling']),
                'oversized_package': float(self.addon_prices['oversized_package'])
            },
            'service_area': [city.title() for city in self.allowed_cities]
        }