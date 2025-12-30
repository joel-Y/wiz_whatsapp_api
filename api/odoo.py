from http.server import BaseHTTPRequestHandler
import json
import xmlrpc.client
import os

# Odoo Configuration - SECURE: Using Environment Variables
ODOO_URL = os.environ.get('ODOO_URL', 'https://wizsmith.com')
ODOO_DB = os.environ.get('ODOO_DB', 'Wiz')
ODOO_USERNAME = os.environ.get('ODOO_USERNAME')
ODOO_PASSWORD = os.environ.get('ODOO_PASSWORD')

# Validate that credentials are set
if not ODOO_USERNAME or not ODOO_PASSWORD:
    raise ValueError("ODOO_USERNAME and ODOO_PASSWORD must be set as environment variables")

def get_odoo_uid():
    """Authenticate with Odoo and return UID"""
    try:
        common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
        uid = common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD, {})
        if not uid:
            raise ValueError("Odoo authentication failed - check credentials")
        return uid
    except Exception as e:
        raise Exception(f"Failed to connect to Odoo: {str(e)}")

class handler(BaseHTTPRequestHandler):
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-API-Key')
        self.end_headers()
    
    def do_POST(self):
        """Handle Odoo API requests"""
        try:
            # Read request body
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            request_json = json.loads(post_data.decode('utf-8'))
            
            # Get action from request
            action = request_json.get('action')
            
            if not action:
                raise ValueError("Missing 'action' parameter")
            
            # Connect to Odoo
            uid = get_odoo_uid()
            models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')
            
            result = {}
            
            # ===== ACTION: Search Customer by Phone =====
            if action == 'search_customer':
                phone = request_json.get('phone', '').strip()
                
                if not phone:
                    result = {
                        'success': False,
                        'error': 'Phone number is required'
                    }
                else:
                    customers = models.execute_kw(
                        ODOO_DB, uid, ODOO_PASSWORD,
                        'res.partner', 'search_read',
                        [[['phone', 'ilike', phone]]],
                        {'fields': ['id', 'name', 'email', 'phone', 'street', 'city', 'country_id'], 'limit': 5}
                    )
                    result = {
                        'success': True,
                        'action': 'search_customer',
                        'count': len(customers),
                        'customers': customers
                    }
            
            # ===== ACTION: Get Customer by ID =====
            elif action == 'get_customer':
                customer_id = request_json.get('customer_id')
                
                if not customer_id:
                    result = {
                        'success': False,
                        'error': 'customer_id is required'
                    }
                else:
                    customer = models.execute_kw(
                        ODOO_DB, uid, ODOO_PASSWORD,
                        'res.partner', 'read',
                        [[int(customer_id)]],
                        {'fields': ['id', 'name', 'email', 'phone', 'street', 'city', 'zip', 'country_id', 'website']}
                    )
                    result = {
                        'success': True,
                        'action': 'get_customer',
                        'customer': customer[0] if customer else None
                    }
            
            # ===== ACTION: Create Lead =====
            elif action == 'create_lead':
                lead_data = {
                    'name': request_json.get('opportunity_name', 'WhatsApp Lead'),
                    'contact_name': request_json.get('contact_name'),
                    'phone': request_json.get('phone'),
                    'email': request_json.get('email'),
                    'description': request_json.get('description', ''),
                    'source_id': False,
                }
                
                # Remove None values
                lead_data = {k: v for k, v in lead_data.items() if v is not None and v != ''}
                
                if not lead_data.get('phone') and not lead_data.get('email'):
                    result = {
                        'success': False,
                        'error': 'Either phone or email is required'
                    }
                else:
                    lead_id = models.execute_kw(
                        ODOO_DB, uid, ODOO_PASSWORD,
                        'crm.lead', 'create',
                        [lead_data]
                    )
                    result = {
                        'success': True,
                        'action': 'create_lead',
                        'lead_id': lead_id,
                        'message': f'Lead created successfully with ID: {lead_id}'
                    }
            
            # ===== ACTION: List Recent Leads =====
            elif action == 'list_leads':
                limit = request_json.get('limit', 10)
                
                leads = models.execute_kw(
                    ODOO_DB, uid, ODOO_PASSWORD,
                    'crm.lead', 'search_read',
                    [[]],
                    {'fields': ['id', 'name', 'contact_name', 'phone', 'email', 'stage_id', 'expected_revenue', 'create_date'], 
                     'limit': int(limit),
                     'order': 'create_date desc'}
                )
                result = {
                    'success': True,
                    'action': 'list_leads',
                    'count': len(leads),
                    'leads': leads
                }
            
            # ===== ACTION: Update Lead Stage =====
            elif action == 'update_lead_stage':
                lead_id = request_json.get('lead_id')
                stage_id = request_json.get('stage_id')
                
                if not lead_id or not stage_id:
                    result = {
                        'success': False,
                        'error': 'lead_id and stage_id are required'
                    }
                else:
                    models.execute_kw(
                        ODOO_DB, uid, ODOO_PASSWORD,
                        'crm.lead', 'write',
                        [[int(lead_id)], {'stage_id': int(stage_id)}]
                    )
                    result = {
                        'success': True,
                        'action': 'update_lead_stage',
                        'message': f'Lead {lead_id} updated to stage {stage_id}'
                    }
            
            # ===== ACTION: Search Products =====
            elif action == 'search_products':
                search_term = request_json.get('search_term', '').strip()
                
                if not search_term:
                    result = {
                        'success': False,
                        'error': 'search_term is required'
                    }
                else:
                    products = models.execute_kw(
                        ODOO_DB, uid, ODOO_PASSWORD,
                        'product.product', 'search_read',
                        [[['name', 'ilike', search_term], ['sale_ok', '=', True]]],
                        {'fields': ['id', 'name', 'list_price', 'qty_available', 'default_code'], 'limit': 10}
                    )
                    result = {
                        'success': True,
                        'action': 'search_products',
                        'count': len(products),
                        'products': products
                    }
            
            # ===== ACTION: Get Lead Stages =====
            elif action == 'get_lead_stages':
                stages = models.execute_kw(
                    ODOO_DB, uid, ODOO_PASSWORD,
                    'crm.stage', 'search_read',
                    [[]],
                    {'fields': ['id', 'name', 'sequence']}
                )
                result = {
                    'success': True,
                    'action': 'get_lead_stages',
                    'stages': stages
                }
            
            # ===== Unknown Action =====
            else:
                result = {
                    'success': False,
                    'error': f'Unknown action: {action}',
                    'available_actions': [
                        'search_customer',
                        'get_customer',
                        'create_lead',
                        'list_leads',
                        'update_lead_stage',
                        'search_products',
                        'get_lead_stages'
                    ]
                }
            
            # Send successful response
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(result, default=str).encode('utf-8'))
            
        except Exception as e:
            # Error response
            error_result = {
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__
            }
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(error_result).encode('utf-8'))
    
    def do_GET(self):
        """Health check endpoint"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        health = {
            'status': 'ok',
            'service': 'Odoo API Bridge',
            'odoo_url': ODOO_URL,
            'odoo_db': ODOO_DB
        }
        self.wfile.write(json.dumps(health).encode('utf-8'))