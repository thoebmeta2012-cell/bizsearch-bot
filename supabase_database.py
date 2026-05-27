"""
Supabase PostgreSQL Database Adapter for MOC Bot
Provides the same interface as the SQLite Database class
"""

import logging
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from supabase import create_client, Client

logger = logging.getLogger(__name__)


class SupabaseDatabase:
    """Database manager for MOC Bot using Supabase PostgreSQL."""
    
    def __init__(self, url: str = None, key: str = None):
        """
        Initialize Supabase database connection
        
        Args:
            url: Supabase project URL (from env if None)
            key: Supabase service key (from env if None)
        """
        self.url = url or os.getenv('SUPABASE_URL')
        self.key = key or os.getenv('SUPABASE_SERVICE_KEY')
        
        if not self.url or not self.key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        
        self.client: Client = create_client(self.url, self.key)
        logger.info(f"Supabase database initialized: {self.url}")
        
        # Initialize schema
        self.init_database()
    
    def init_database(self):
        """Initialize database with all required tables."""
        logger.info("Supabase tables should be created via SQL migrations")
        logger.info("Run the SQL schema from create_supabase_schema.sql")
        # Note: Supabase tables are created via SQL migrations, not programmatically
    
    # User Management
    def add_or_update_user(self, user_id: int, username: str = None, first_name: str = None, 
                          last_name: str = None, language_code: str = None, is_bot: bool = False):
        """Add new user or update existing user info."""
        try:
            data = {
                'user_id': user_id,
                'username': username,
                'first_name': first_name,
                'last_name': last_name,
                'language_code': language_code,
                'is_bot': is_bot,
                'last_active': datetime.now().isoformat()
            }
            
            # Upsert user
            self.client.table('users').upsert(data, on_conflict='user_id').execute()
        except Exception as e:
            logger.error(f"Error adding/updating user: {e}")
    
    def update_user_activity(self, user_id: int):
        """Update user's last active timestamp."""
        try:
            self.client.table('users').update({
                'last_active': datetime.now().isoformat()
            }).eq('user_id', user_id).execute()
        except Exception as e:
            logger.error(f"Error updating user activity: {e}")
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user information."""
        try:
            response = self.client.table('users').select('*').eq('user_id', user_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin."""
        user = self.get_user(user_id)
        return user and user.get('is_admin', False)
    
    def set_admin(self, user_id: int, is_admin: bool = True):
        """Set user admin status."""
        try:
            self.client.table('users').update({
                'is_admin': is_admin
            }).eq('user_id', user_id).execute()
        except Exception as e:
            logger.error(f"Error setting admin: {e}")
    
    def block_user(self, user_id: int, blocked: bool = True):
        """Block or unblock a user."""
        try:
            self.client.table('users').update({
                'is_blocked': blocked
            }).eq('user_id', user_id).execute()
        except Exception as e:
            logger.error(f"Error blocking user: {e}")
    
    def is_blocked(self, user_id: int) -> bool:
        """Check if user is blocked."""
        user = self.get_user(user_id)
        return user and user.get('is_blocked', False)
    
    def get_all_users(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Get all users with pagination."""
        try:
            response = self.client.table('users').select('*').order('last_active', desc=True).range(offset, offset + limit - 1).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []
    
    def get_user_stats(self) -> Dict:
        """Get overall user statistics."""
        try:
            # This would need a custom RPC function in Supabase for complex aggregations
            # For now, return basic stats
            response = self.client.table('users').select('*', count='exact').execute()
            return {
                'total_users': response.count or 0
            }
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return {}
    
    # Director Search Management Methods
    def add_director_search(
        self, 
        user_id: int, 
        search_term: str,
        results_count: int = 0,
        duration: float = 0,
        from_cache: bool = False,
        cached: bool = False
    ) -> int:
        """Add director search to history and return search_id."""
        try:
            normalized = search_term.lower().strip()
            
            data = {
                'user_id': user_id,
                'search_term': search_term,
                'search_term_normalized': normalized,
                'results_count': results_count,
                'duration': duration,
                'from_cache': from_cache,
                'cached': cached
            }
            
            response = self.client.table('director_searches').insert(data).execute()
            
            # Update user's total searches
            self.client.rpc('increment_user_searches', {'p_user_id': user_id}).execute()
            
            return response.data[0]['id'] if response.data else None
        except Exception as e:
            logger.error(f"Error adding director search: {e}")
            return None
    
    def add_director_result(self, search_id: int, result_data: Dict):
        """Add a director search result to database."""
        try:
            data = {
                'search_id': search_id,
                'person_name': result_data.get('person_name'),
                'company_name': result_data.get('company_name'),
                'registration_number': result_data.get('registration_number'),
                'role': result_data.get('role'),
                'status': result_data.get('status'),
                'company_type': result_data.get('company_type', '')
            }
            
            self.client.table('director_results').insert(data).execute()
        except Exception as e:
            logger.error(f"Error adding director result: {e}")
    
    def update_director_search_cache_status(self, search_id: int, cached: bool):
        """Update the cache status of a director search."""
        try:
            self.client.table('director_searches').update({
                'cached': cached
            }).eq('id', search_id).execute()
        except Exception as e:
            logger.error(f"Error updating cache status: {e}")
    
    def get_director_searches(
        self, 
        user_id: Optional[int] = None,
        limit: int = 20,
        since: Optional[datetime] = None
    ) -> List[Dict]:
        """Get director search history."""
        try:
            query = self.client.table('director_searches').select('*')
            
            if user_id is not None:
                query = query.eq('user_id', user_id)
            
            if since is not None:
                query = query.gte('created_at', since.isoformat())
            
            response = query.order('created_at', desc=True).limit(limit).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting director searches: {e}")
            return []
    
    def get_director_results(self, search_id: int) -> List[Dict]:
        """Get results for a specific director search."""
        try:
            response = self.client.table('director_results').select('*').eq('search_id', search_id).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting director results: {e}")
            return []
    
    def get_director_search_stats(self) -> Dict:
        """Get director search statistics."""
        try:
            # Use RPC function for complex aggregations
            response = self.client.rpc('get_director_search_stats').execute()
            return response.data[0] if response.data else {}
        except Exception as e:
            logger.error(f"Error getting director search stats: {e}")
            return {}
    
    def get_popular_directors(self, limit: int = 10) -> List[Dict]:
        """Get most searched directors."""
        try:
            response = self.client.rpc('get_popular_directors', {'p_limit': limit}).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting popular directors: {e}")
            return []
    
    def update_user_search_mode(self, user_id: int, mode: str):
        """Update user's last search mode preference."""
        try:
            self.client.table('users').update({
                'last_search_mode': mode
            }).eq('user_id', user_id).execute()
        except Exception as e:
            logger.error(f"Error updating search mode: {e}")
    
    def get_user_search_mode(self, user_id: int) -> str:
        """Get user's last search mode preference."""
        user = self.get_user(user_id)
        if user and 'last_search_mode' in user:
            return user['last_search_mode'] or 'company'
        return 'company'
    
    # Cache Management Methods (simplified for Supabase)
    def get_cached_search(self, search_term: str, entity_type: str = "Companies"):
        """Retrieve cached search from database."""
        try:
            normalized = search_term.lower().strip()
            response = self.client.table('cached_searches').select('*').eq(
                'search_term_normalized', normalized
            ).eq('entity_type', entity_type).gt('expires_at', datetime.now().isoformat()).execute()
            
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Error getting cached search: {e}")
            return None
    
    def store_cached_search(
        self,
        search_term: str,
        entity_type: str,
        results_json: str,
        results_count: int,
        expires_at: datetime,
        source: str = "live_search"
    ) -> Optional[int]:
        """Store search results in cache."""
        try:
            normalized = search_term.lower().strip()
            
            data = {
                'search_term': search_term,
                'search_term_normalized': normalized,
                'entity_type': entity_type,
                'results_json': results_json,
                'results_count': results_count,
                'expires_at': expires_at.isoformat(),
                'source': source
            }
            
            response = self.client.table('cached_searches').upsert(
                data, 
                on_conflict='search_term_normalized,entity_type'
            ).execute()
            
            return response.data[0]['id'] if response.data else None
        except Exception as e:
            logger.error(f"Error storing cached search: {e}")
            return None
    
    def update_cache_access(self, cache_id: int) -> bool:
        """Update last_accessed timestamp and increment access_count."""
        try:
            # Cast to bigint to avoid function overloading ambiguity
            self.client.rpc('update_cache_access', {'p_cache_id': int(cache_id)}).execute()
            return True
        except Exception as e:
            logger.error(f"Error updating cache access: {e}")
            # Don't fail the request if cache update fails
            return False
    
    # Placeholder methods for compatibility
    def add_search(self, user_id: int, search_term: str, entity_type: str = 'Companies',
                   results_count: int = 0, max_pages: int = 10, duration: float = 0,
                   from_cache: bool = False, cached: bool = False) -> int:
        """Add company search to history."""
        try:
            data = {
                'user_id': user_id,
                'search_term': search_term,
                'entity_type': entity_type,
                'results_count': results_count,
                'max_pages': max_pages,
                'search_duration': duration,
                'from_cache': from_cache,
                'cached': cached
            }
            
            response = self.client.table('search_history').insert(data).execute()
            
            # Update user's total searches
            self.client.rpc('increment_user_searches', {'p_user_id': user_id}).execute()
            
            return response.data[0]['id'] if response.data else None
        except Exception as e:
            logger.error(f"Error adding search: {e}")
            return None
    
    def add_search_result(self, search_id: int, result_data: Dict):
        """Add a company search result to database."""
        try:
            # Convert directors list to JSON if present
            import json
            directors_json = json.dumps([d.to_dict() for d in result_data.get('directors', [])])
            
            data = {
                'search_id': search_id,
                'entity_name': result_data.get('entity_name'),
                'entity_name_khmer': result_data.get('entity_name_khmer'),
                'registration_number': result_data.get('registration_number'),
                'original_id': result_data.get('original_id'),
                'status': result_data.get('status'),
                'registration_date': result_data.get('registration_date'),
                're_registration_date': result_data.get('re_registration_date'),
                'entity_type': result_data.get('entity_type'),
                'address': result_data.get('address'),
                'tin': result_data.get('tin'),
                'tax_registration_date': result_data.get('tax_registration_date'),
                'annual_return_date': result_data.get('annual_return_date'),
                'details_fetched': int(bool(result_data.get('directors'))),
                'directors_json': directors_json
            }
            
            # Insert search result
            self.client.table('search_results').insert(data).execute()
        except Exception as e:
            error_msg = str(e)
            # Check if table doesn't exist
            if 'PGRST205' in error_msg or 'search_results' in error_msg:
                logger.warning(f"search_results table not found. Please run fix_supabase_tables.sql")
                logger.warning(f"SQL: CREATE TABLE IF NOT EXISTS search_results (...)")
            else:
                logger.error(f"Error adding search result: {e}")
    
    def update_search_cache_status(self, search_id: int, cached: bool):
        """Update the cache status of a search."""
        try:
            self.client.table('search_history').update({
                'cached': cached
            }).eq('id', search_id).execute()
        except Exception as e:
            logger.error(f"Error updating search cache status: {e}")
    
    def log_interaction(self, user_id: int, interaction_type: str, command: str = None,
                       message_text: str = None, callback_data: str = None, 
                       success: bool = True, error_message: str = None):
        """Log user interaction."""
        try:
            data = {
                'user_id': user_id,
                'interaction_type': interaction_type,
                'command': command,
                'message_text': message_text,
                'callback_data': callback_data,
                'success': success,
                'error_message': error_message
            }
            
            self.client.table('interactions').insert(data).execute()
        except Exception as e:
            logger.error(f"Error logging interaction: {e}")
    
    def add_export(self, user_id: int, search_id: int = None, export_type: str = 'csv',
                   filename: str = None, records_count: int = 0) -> int:
        """Log export activity."""
        try:
            data = {
                'user_id': user_id,
                'search_id': search_id,
                'export_type': export_type,
                'filename': filename,
                'records_count': records_count
            }
            
            response = self.client.table('exports').insert(data).execute()
            
            # Update user's total exports
            self.client.rpc('increment_user_exports', {'p_user_id': user_id}).execute()
            
            return response.data[0]['id'] if response.data else None
        except Exception as e:
            logger.error(f"Error adding export: {e}")
            return None

    # Search History Methods
    def get_user_search_history(self, user_id: int, limit: int = 20) -> List[Dict]:
        """Get user's search history."""
        try:
            response = self.client.table('search_history').select('*').eq(
                'user_id', user_id
            ).order('created_at', desc=True).limit(limit).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting user search history: {e}")
            return []
    
    def get_search_results(self, search_id: int) -> List[Dict]:
        """Get results for a specific search."""
        try:
            response = self.client.table('search_results').select('*').eq('search_id', search_id).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting search results: {e}")
            return []
    
    # Statistics and Analytics
    def get_search_stats(self) -> Dict:
        """Get search statistics."""
        try:
            # Use RPC function for complex aggregations
            response = self.client.rpc('get_search_stats').execute()
            if response.data:
                return response.data[0]
            
            # Fallback to basic stats if RPC doesn't exist
            total_response = self.client.table('search_history').select('*', count='exact').execute()
            today_response = self.client.table('search_history').select('*', count='exact').gte(
                'created_at', datetime.now().date().isoformat()
            ).execute()
            
            return {
                'total_searches': total_response.count or 0,
                'searches_today': today_response.count or 0,
                'searches_week': 0,
                'total_results': 0,
                'avg_results_per_search': 0,
                'avg_duration': 0,
                'unique_users': 0
            }
        except Exception as e:
            logger.error(f"Error getting search stats: {e}")
            return {
                'total_searches': 0,
                'searches_today': 0,
                'searches_week': 0,
                'total_results': 0,
                'avg_results_per_search': 0,
                'avg_duration': 0,
                'unique_users': 0
            }
    
    def get_popular_searches(self, limit: int = 10) -> List[Dict]:
        """Get most popular search terms."""
        try:
            # Use RPC function for aggregation
            response = self.client.rpc('get_popular_searches', {'p_limit': limit}).execute()
            if response.data:
                return response.data
            
            # Fallback: get recent searches
            response = self.client.table('search_history').select(
                'search_term'
            ).order('created_at', desc=True).limit(limit).execute()
            
            # Count occurrences manually
            search_counts = {}
            for row in response.data:
                term = row['search_term'].lower()
                search_counts[term] = search_counts.get(term, 0) + 1
            
            return [
                {'search_term': term, 'search_count': count}
                for term, count in sorted(search_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
            ]
        except Exception as e:
            logger.error(f"Error getting popular searches: {e}")
            return []
    
    def get_database_size(self) -> Dict:
        """Get database size information."""
        try:
            # Get table counts
            tables = ['users', 'search_history', 'search_results', 'interactions', 
                     'exports', 'broadcasts', 'admin_logs']
            
            counts = {}
            for table in tables:
                try:
                    response = self.client.table(table).select('*', count='exact').execute()
                    counts[f"{table}_count"] = response.count or 0
                except Exception as e:
                    logger.warning(f"Could not get count for table {table}: {e}")
                    counts[f"{table}_count"] = 0
            
            # Supabase doesn't expose database size directly, estimate from row counts
            # Rough estimate: 1KB per row average
            total_rows = sum(counts.values())
            estimated_size_mb = (total_rows * 1024) / (1024 * 1024)
            
            return {
                'size_mb': round(estimated_size_mb, 2),
                'size_bytes': int(total_rows * 1024),
                **counts
            }
        except Exception as e:
            logger.error(f"Error getting database size: {e}")
            return {
                'size_mb': 0,
                'users_count': 0,
                'search_history_count': 0,
                'search_results_count': 0,
                'interactions_count': 0,
                'exports_count': 0,
                'broadcasts_count': 0,
                'admin_logs_count': 0
            }
    
    # Broadcast Management
    def create_broadcast(self, admin_id: int, message_text: str, target_type: str = 'all') -> int:
        """Create a new broadcast."""
        try:
            # Count target users
            if target_type == 'all':
                response = self.client.table('users').select('*', count='exact').eq('is_blocked', False).execute()
            elif target_type == 'active':
                week_ago = (datetime.now() - timedelta(days=7)).isoformat()
                response = self.client.table('users').select('*', count='exact').eq(
                    'is_blocked', False
                ).gte('last_active', week_ago).execute()
            else:
                response = self.client.table('users').select('*', count='exact').eq('is_blocked', False).execute()
            
            total_users = response.count or 0
            
            data = {
                'admin_id': admin_id,
                'message_text': message_text,
                'target_type': target_type,
                'total_users': total_users
            }
            
            result = self.client.table('broadcasts').insert(data).execute()
            return result.data[0]['id'] if result.data else None
        except Exception as e:
            logger.error(f"Error creating broadcast: {e}")
            return None
    
    def update_broadcast_status(self, broadcast_id: int, successful: int, failed: int, status: str = 'completed'):
        """Update broadcast status."""
        try:
            self.client.table('broadcasts').update({
                'successful_sends': successful,
                'failed_sends': failed,
                'status': status,
                'completed_at': datetime.now().isoformat()
            }).eq('id', broadcast_id).execute()
        except Exception as e:
            logger.error(f"Error updating broadcast status: {e}")
    
    def get_broadcast_targets(self, target_type: str = 'all') -> List[int]:
        """Get list of user IDs for broadcast."""
        try:
            if target_type == 'all':
                response = self.client.table('users').select('user_id').eq('is_blocked', False).execute()
            elif target_type == 'active':
                week_ago = (datetime.now() - timedelta(days=7)).isoformat()
                response = self.client.table('users').select('user_id').eq(
                    'is_blocked', False
                ).gte('last_active', week_ago).execute()
            else:
                response = self.client.table('users').select('user_id').eq('is_blocked', False).execute()
            
            return [row['user_id'] for row in response.data]
        except Exception as e:
            logger.error(f"Error getting broadcast targets: {e}")
            return []
    
    def get_broadcasts(self, limit: int = 20) -> List[Dict]:
        """Get broadcast history."""
        try:
            response = self.client.table('broadcasts').select(
                '*, users!broadcasts_admin_id_fkey(username)'
            ).order('created_at', desc=True).limit(limit).execute()
            
            # Flatten the nested user data
            broadcasts = []
            for row in response.data:
                broadcast = dict(row)
                if 'users' in broadcast and broadcast['users']:
                    broadcast['admin_username'] = broadcast['users'].get('username')
                    del broadcast['users']
                else:
                    broadcast['admin_username'] = None
                broadcasts.append(broadcast)
            
            return broadcasts
        except Exception as e:
            logger.error(f"Error getting broadcasts: {e}")
            return []
    
    # Admin Logging
    def log_admin_action(self, admin_id: int, action: str, target_user_id: int = None, details: str = None):
        """Log admin action."""
        try:
            data = {
                'admin_id': admin_id,
                'action': action,
                'target_user_id': target_user_id,
                'details': details
            }
            self.client.table('admin_logs').insert(data).execute()
        except Exception as e:
            logger.error(f"Error logging admin action: {e}")
    
    def get_admin_logs(self, limit: int = 100) -> List[Dict]:
        """Get admin action logs."""
        try:
            response = self.client.table('admin_logs').select(
                '*, users!admin_logs_admin_id_fkey(username)'
            ).order('created_at', desc=True).limit(limit).execute()
            
            # Flatten the nested user data
            logs = []
            for row in response.data:
                log = dict(row)
                if 'users' in log and log['users']:
                    log['admin_username'] = log['users'].get('username')
                    del log['users']
                else:
                    log['admin_username'] = None
                logs.append(log)
            
            return logs
        except Exception as e:
            logger.error(f"Error getting admin logs: {e}")
            return []

    # Company Details Storage Methods
    def store_company_details(
        self,
        registration_number: str,
        company_data: Dict,
        directors: List[Dict] = None
    ) -> int:
        """
        Store complete company details including directors permanently
        
        Args:
            registration_number: Company registration number
            company_data: Dictionary with company information
            directors: List of director dictionaries
            
        Returns:
            company_id: ID of stored company
        """
        try:
            import json
            
            # Prepare data
            data = {
                'registration_number': registration_number,
                'entity_name': company_data.get('entity_name'),
                'entity_name_khmer': company_data.get('entity_name_khmer'),
                'original_id': company_data.get('original_id'),
                'status': company_data.get('status'),
                'registration_date': company_data.get('registration_date'),
                're_registration_date': company_data.get('re_registration_date'),
                'entity_type': company_data.get('entity_type'),
                'address': company_data.get('address'),
                'tin': company_data.get('tin'),
                'tax_registration_date': company_data.get('tax_registration_date'),
                'annual_return_date': company_data.get('annual_return_date'),
                'directors_json': json.dumps(directors) if directors else '[]',
                'details_fetched': True,
                'details_fetched_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            # Upsert company details
            response = self.client.table('companies').upsert(
                data, 
                on_conflict='registration_number'
            ).execute()
            
            if response.data:
                logger.info(f"✅ Stored company details: {registration_number}")
                return response.data[0].get('id', 0)
            
            return 0
            
        except Exception as e:
            logger.error(f"Error storing company details: {e}")
            return 0
    
    def company_details_exist(self, registration_number: str) -> bool:
        """Check if company details exist in database."""
        try:
            response = self.client.table('companies').select('id').eq(
                'registration_number', registration_number
            ).eq('details_fetched', True).execute()
            
            return len(response.data) > 0
            
        except Exception as e:
            logger.error(f"Error checking company details: {e}")
            return False
    
    def get_company_details(self, registration_number: str) -> Optional[Dict]:
        """Get complete company details from database."""
        try:
            import json
            
            response = self.client.table('companies').select('*').eq(
                'registration_number', registration_number
            ).eq('details_fetched', True).execute()
            
            if not response.data:
                return None
            
            company = response.data[0]
            
            # Parse directors JSON
            directors = []
            if company.get('directors_json'):
                try:
                    directors = json.loads(company['directors_json'])
                except:
                    directors = []
            
            return {
                'registration_number': company['registration_number'],
                'entity_name': company['entity_name'],
                'entity_name_khmer': company.get('entity_name_khmer'),
                'original_id': company.get('original_id'),
                'status': company.get('status'),
                'registration_date': company.get('registration_date'),
                're_registration_date': company.get('re_registration_date'),
                'entity_type': company.get('entity_type'),
                'address': company.get('address'),
                'tin': company.get('tin'),
                'tax_registration_date': company.get('tax_registration_date'),
                'annual_return_date': company.get('annual_return_date'),
                'directors': directors
            }
            
        except Exception as e:
            logger.error(f"Error getting company details: {e}")
            return None
    
    def get_company_stats(self) -> Dict:
        """Get statistics about stored companies."""
        try:
            # Total companies
            total_response = self.client.table('companies').select(
                'id', count='exact'
            ).execute()
            total = total_response.count if hasattr(total_response, 'count') else 0
            
            # Companies with details
            details_response = self.client.table('companies').select(
                'id', count='exact'
            ).eq('details_fetched', True).execute()
            with_details = details_response.count if hasattr(details_response, 'count') else 0
            
            return {
                'total_companies': total,
                'companies_with_details': with_details,
                'total_directors': 0  # Would need separate query
            }
            
        except Exception as e:
            logger.error(f"Error getting company stats: {e}")
            return {
                'total_companies': 0,
                'companies_with_details': 0,
                'total_directors': 0
            }

    # API Key Management Methods
    def create_api_key(self, key: str, name: str, rate_limit: int = 60, daily_limit: int = 10000):
        """Create a new API key"""
        try:
            data = {
                'key': key,
                'name': name,
                'rate_limit': rate_limit,
                'daily_limit': daily_limit,
                'is_active': True,
                'total_requests': 0,
                'created_at': datetime.now().isoformat()
            }
            self.client.table('api_keys').insert(data).execute()
            logger.info(f"Created API key: {name}")
        except Exception as e:
            logger.error(f"Error creating API key: {e}")
            raise
    
    def get_all_api_keys(self) -> List[Dict]:
        """Get all API keys"""
        try:
            response = self.client.table('api_keys').select('*').order('created_at', desc=True).execute()
            
            keys = []
            for row in response.data:
                keys.append({
                    'id': row['id'],
                    'key': row['key'][:10] + '...',  # Masked
                    'name': row['name'],
                    'rate_limit': row['rate_limit'],
                    'daily_limit': row['daily_limit'],
                    'is_active': row['is_active'],
                    'total_requests': row.get('total_requests', 0),
                    'created_at': row['created_at'],
                    'last_used': row.get('last_used')
                })
            
            return keys
        except Exception as e:
            logger.error(f"Error getting all API keys: {e}")
            return []
    
    def revoke_api_key(self, key_id: int):
        """Revoke an API key"""
        try:
            self.client.table('api_keys').update({
                'is_active': False
            }).eq('id', key_id).execute()
            logger.info(f"Revoked API key ID: {key_id}")
        except Exception as e:
            logger.error(f"Error revoking API key: {e}")
            raise
    
    def get_api_key_info(self, api_key: str) -> Optional[Dict]:
        """Get API key information"""
        try:
            response = self.client.table('api_keys').select('*').eq('key', api_key).execute()
            
            if not response.data:
                return None
            
            row = response.data[0]
            return {
                'id': row['id'],
                'name': row['name'],
                'rate_limit': row['rate_limit'],
                'daily_limit': row['daily_limit'],
                'is_active': row['is_active']
            }
        except Exception as e:
            logger.error(f"Error getting API key info: {e}")
            return None
    
    def get_api_key_usage(self, api_key: str) -> Dict:
        """Get usage statistics for an API key"""
        try:
            # Get API key info
            key_response = self.client.table('api_keys').select('*').eq('key', api_key).execute()
            
            if not key_response.data:
                return {}
            
            key_data = key_response.data[0]
            
            # Get usage logs
            logs_response = self.client.table('api_usage_logs').select('*').eq(
                'api_key', api_key
            ).order('timestamp', desc=True).limit(100).execute()
            
            return {
                'key': api_key[:10] + '...',
                'name': key_data['name'],
                'total_requests': key_data.get('total_requests', 0),
                'rate_limit': key_data['rate_limit'],
                'daily_limit': key_data['daily_limit'],
                'last_used': key_data.get('last_used'),
                'recent_logs': logs_response.data if logs_response.data else []
            }
        except Exception as e:
            logger.error(f"Error getting API key usage: {e}")
            return {}

    def get_usage_stats(self, start_date: str, end_date: str, days: int = 30) -> Dict:
        """Get system-wide usage statistics using RPC functions"""
        try:
            # Call the RPC function for usage stats
            stats_response = self.client.rpc('get_api_usage_stats', {'p_days': days}).execute()
            
            if not stats_response.data or len(stats_response.data) == 0:
                return self._empty_usage_stats()
            
            stats = stats_response.data[0]
            
            # Get top API keys
            top_keys_response = self.client.rpc('get_top_api_keys', {'p_days': days, 'p_limit': 10}).execute()
            top_api_keys = top_keys_response.data if top_keys_response.data else []
            
            # Get top queries
            top_queries_response = self.client.rpc('get_top_queries', {'p_days': days, 'p_limit': 10}).execute()
            top_queries = top_queries_response.data if top_queries_response.data else []
            
            # Get endpoint usage
            endpoint_response = self.client.rpc('get_endpoint_usage', {'p_days': days}).execute()
            endpoint_usage = {}
            if endpoint_response.data:
                for row in endpoint_response.data:
                    endpoint_usage[row['endpoint']] = row['count']
            
            return {
                'total_requests': stats.get('total_requests', 0),
                'requests_today': stats.get('requests_today', 0),
                'requests_this_week': stats.get('requests_this_week', 0),
                'requests_this_month': stats.get('requests_this_month', 0),
                'cache_hit_rate': float(stats.get('cache_hit_rate', 0.0)),
                'avg_response_time': float(stats.get('avg_response_time', 0.0)),
                'top_api_keys': top_api_keys,
                'top_queries': top_queries,
                'endpoint_usage': endpoint_usage
            }
        except Exception as e:
            logger.error(f"Error getting usage stats: {e}")
            return self._empty_usage_stats()
    
    def _empty_usage_stats(self) -> Dict:
        """Return empty usage stats structure"""
        return {
            'total_requests': 0,
            'requests_today': 0,
            'requests_this_week': 0,
            'requests_this_month': 0,
            'cache_hit_rate': 0.0,
            'avg_response_time': 0.0,
            'top_api_keys': [],
            'top_queries': [],
            'endpoint_usage': {}
        }

    def get_recent_activity(self, limit: int = 50) -> List[Dict]:
        """Get recent API activity logs"""
        try:
            response = self.client.table('api_usage_logs').select('*').order(
                'timestamp', desc=True
            ).limit(limit).execute()
            
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Error getting recent activity: {e}")
            return []
