from http.server import BaseHTTPRequestHandler
import json
import xmlrpc.client
import os

class handler(BaseHTTPRequestHandler):
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-API-Key')
        self.end_headers()
    
    def get_odoo_connection(self):
        """Get Odoo credentials and authenticate - called per request"""
        # Get credentials from environment
        ODOO_URL = os.environ.get('ODOO_URL', 'https://wizsmith.com')
        ODOO_DB = os.environ.get('ODOO_DB', 'Wiz')
        ODOO_USERNAME = os.environ.get('ODOO_USERNAME')
        ODOO_PASSWORD = os.environ.get('ODOO_PASSWORD')
        
        # Validate credentials exist
        if not ODOO_USERNAME or not ODOO_PASSWORD:
            raise ValueError(f"Missing credentials - Username: {bool(ODOO_USERNAME)}, Password: {bool(ODOO_PASSWORD)}")
        
        # Authenticate with Odoo
        try:
            common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
            uid = common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD, {})
            
            if not uid:
                raise ValueError(f"Authentication failed for user: {ODOO_USERNAME} on database: {ODOO_DB}")
            
            models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')
            
            return {
                'uid': uid,
                'models': models,
                'url': ODOO_URL,
                'db': ODOO_DB,
                'password': ODOO_PASSWORD
            }
            
        except Exception as e:
            raise Exception(f"Odoo connection failed: {str(e)}")
    
    def do_GET(self):
        """Health check endpoint"""
        try:
            # Get credentials
            ODOO_URL = os.environ.get('ODOO_URL', 'https://wizsmith.com')
            ODOO_DB = os.environ.get('ODOO_DB', 'Wiz')
            ODOO_USERNAME = os.environ.get('ODOO_USERNAME')
            ODOO_PASSWORD = os.environ.get('ODOO_PASSWORD')
            
            credentials_set = bool(ODOO_URL and ODOO_DB and ODOO_USERNAME and ODOO_PASSWORD)
            
            # Try to authenticate if credentials are set
            auth_test = None
            if credentials_set:
                try:
                    common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
                    uid = common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD, {})
                    auth_test = {
                        'authenticated': bool(uid),
                        'uid': uid if uid else None
                    }
                except Exception as e:
                    auth_test = {
                        'authenticated': False,
                        'error': str(e)
                    }
            
            health = {
                'status': 'ok',
                'service': 'Odoo API Bridge',
                'odoo_url': ODOO_URL,
                'odoo_db': ODOO_DB,
                'credentials_set': credentials_set,
                'has_username': bool(ODOO_USERNAME),
                'has_password': bool(ODOO_PASSWORD),
                'auth_test': auth_test
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(health, default=str).encode('utf-8'))
            
        except Exception as e:
            error = {
                'status': 'error',
                'error': str(e)
            }
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(error).encode('utf-8'))
    
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
            
            # Connect to Odoo (per request)
            odoo = self.get_odoo_connection()
            
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
                    # Try multiple phone formats
                    customers = odoo['models'].execute_kw(
                        odoo['db'], odoo['uid'], odoo['password'],
                        'res.partner', 'search_read',
                        [[['|', ['phone', 'ilike', phone], ['mobile', 'ilike', phone]]]],
                        {'fields': ['id', 'name', 'email', 'phone', 'mobile', 'street', 'city', 'country_id'], 'limit': 5}
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
                    customer = odoo['models'].execute_kw(
                        odoo['db'], odoo['uid'], odoo['password'],
                        'res.partner', 'read',
                        [[int(customer_id)]],
                        {'fields': ['id', 'name', 'email', 'phone', 'mobile', 'street', 'city', 'zip', 'country_id', 'website']}
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
                    'email_from': request_json.get('email'),
                    'description': request_json.get('description', ''),
                }
                
                # Remove None values
                lead_data = {k: v for k, v in lead_data.items() if v is not None and v != ''}
                
                if not lead_data.get('phone') and not lead_data.get('email_from'):
                    result = {
                        'success': False,
                        'error': 'Either phone or email is required'
                    }
                else:
                    lead_id = odoo['models'].execute_kw(
                        odoo['db'], odoo['uid'], odoo['password'],
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
                
                leads = odoo['models'].execute_kw(
                    odoo['db'], odoo['uid'], odoo['password'],
                    'crm.lead', 'search_read',
                    [[]],
                    {'fields': ['id', 'name', 'contact_name', 'phone', 'email_from', 'stage_id', 'expected_revenue', 'create_date'], 
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
                    odoo['models'].execute_kw(
                        odoo['db'], odoo['uid'], odoo['password'],
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
                    products = odoo['models'].execute_kw(
                        odoo['db'], odoo['uid'], odoo['password'],
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
                stages = odoo['models'].execute_kw(
                    odoo['db'], odoo['uid'], odoo['password'],
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