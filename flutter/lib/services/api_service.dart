import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

class ApiService {
  static String _baseUrl = 'https://api.dawaiflow.com';
  static String? _token;
  static bool _isDiscoveringBaseUrl = false;
  static DateTime? _lastDiscoveryTime;

  static String get baseUrl => _baseUrl;

  static final List<String> _candidateUrls = [
    'https://api.dawaiflow.com', // Production backend (PRIMARY ONLINE)
    'http://10.0.2.2:8000',      // Android Emulator loopback fallback
    'http://192.168.29.8:8000',  // Local Wi-Fi LAN host fallback
    'http://127.0.0.1:8000',     // Local desktop loopback fallback
    'http://localhost:8000',     // Standard localhost fallback
  ];

  static void setBaseUrl(String url) {
    if (url.endsWith('/')) {
      _baseUrl = url.substring(0, url.length - 1);
    } else {
      _baseUrl = url;
    }
  }

  static void setToken(String token) {
    _token = token;
    debugPrint('[DIAGNOSTIC] setToken: Token updated (Length: ${token.length})');
  }

  static String? getToken() {
    return _token;
  }

  /// Dynamically probes available backend server addresses to find the fastest responding host.
  /// Uses caching and parallel probing to eliminate 10s timeout delays on mobile networks.
  static Future<String> discoverWorkingBaseUrl() async {
    if (kIsWeb || _isDiscoveringBaseUrl) return _baseUrl;

    // Return cached base URL if verified within the last 60 seconds
    if (_lastDiscoveryTime != null &&
        DateTime.now().difference(_lastDiscoveryTime!).inSeconds < 60) {
      return _baseUrl;
    }

    _isDiscoveringBaseUrl = true;

    // First check currently configured _baseUrl with 3500ms timeout for mobile latency
    try {
      final res = await http.get(
        Uri.parse('$_baseUrl/health'),
        headers: {'User-Agent': 'DawaiFlowMobile/1.0'},
      ).timeout(const Duration(milliseconds: 3500));
      if (res.statusCode == 200) {
        _lastDiscoveryTime = DateTime.now();
        _isDiscoveringBaseUrl = false;
        return _baseUrl;
      }
    } catch (_) {}

    debugPrint('[Host Discovery] Probing candidate backend URLs concurrently for mobile connectivity...');

    // Parallel candidate probing to avoid sequential 1.5s x 5 delay
    final tasks = _candidateUrls.map((candidate) async {
      try {
        final res = await http.get(
          Uri.parse('$candidate/health'),
          headers: {'User-Agent': 'DawaiFlowMobile/1.0'},
        ).timeout(const Duration(milliseconds: 2500));
        if (res.statusCode == 200) {
          return candidate;
        }
      } catch (_) {}
      return null;
    }).toList();

    final results = await Future.wait(tasks);
    final workingHost = results.firstWhere((url) => url != null, orElse: () => null);

    if (workingHost != null) {
      _baseUrl = workingHost;
      debugPrint('[Host Discovery] SUCCESS! Connected to backend host: $_baseUrl');
    } else {
      debugPrint('[Host Discovery] Fallback to primary base URL: $_baseUrl');
    }

    _lastDiscoveryTime = DateTime.now();
    _isDiscoveringBaseUrl = false;
    return _baseUrl;
  }

  /// Ensures a valid Bearer JWT token exists before executing API requests.
  /// Performs transparent host discovery and auto-restoration on cold start.
  static Future<bool> ensureAuthenticated() async {
    await discoverWorkingBaseUrl();

    if (_token != null && _token!.isNotEmpty) {
      return true;
    }

    // Never auto-authenticate with hardcoded credentials in release/production builds
    if (kReleaseMode) {
      debugPrint('[Auth Guard] Token missing in release mode. User authentication required.');
      return false;
    }

    // In debug mode, allow dev login with default pilot account or dart-define
    const devEmail = String.fromEnvironment('DEV_AUTH_EMAIL', defaultValue: 'sharma@example.com');
    const devPass = String.fromEnvironment('DEV_AUTH_PASSWORD', defaultValue: 'password123');
    if (devEmail.isNotEmpty && devPass.isNotEmpty) {
      debugPrint('[Auth Guard] Debug mode: Attempting auto-login with environment credentials...');
      final success = await login(devEmail, devPass);
      if (success) {
        debugPrint('[Auth Guard] Debug auto-restoration successful!');
      } else {
        debugPrint('[Auth Guard] Debug auto-restoration failed.');
      }
      return success;
    }

    debugPrint('[Auth Guard] Token missing. User must authenticate via login screen.');
    return false;
  }

  static Map<String, String> _getHeaders() {
    final tokenToUse = _token;
    return {
      'Content-Type': 'application/json',
      'User-Agent': 'DawaiFlowMobile/1.0',
      if (tokenToUse != null && tokenToUse.isNotEmpty)
        'Authorization': 'Bearer $tokenToUse',
    };
  }

  /// Authenticate and retrieve session token across candidate host URLs
  static Future<bool> login(String email, String password) async {
    debugPrint('[DIAGNOSTIC] Initiating login for email: $email');

    final candidateUrls = [
      'https://api.dawaiflow.com',
      _baseUrl,
      'http://10.0.2.2:8000',
      'http://192.168.29.8:8000',
      'http://127.0.0.1:8000',
      'http://localhost:8000',
    ];

    for (final base in candidateUrls) {
      if (base.isEmpty && !kIsWeb) continue;
      final endpoint = '$base/login';
      try {
        debugPrint('[DIAGNOSTIC] Attempting POST $endpoint');
        final response = await http.post(
          Uri.parse(endpoint),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'email': email, 'password': password}),
        ).timeout(const Duration(seconds: 4));

        debugPrint('[DIAGNOSTIC] POST $endpoint -> HTTP Status: ${response.statusCode}');

        if (response.statusCode == 200) {
          final data = jsonDecode(response.body);
          _token = data['access_token'];
          _baseUrl = base;
          debugPrint('[DIAGNOSTIC] AUTH USER TOKEN SET: ${_token?.substring(0, 15)}...');
          debugPrint('[DIAGNOSTIC] API BASE URL SET TO: $_baseUrl');
          return true;
        }
      } catch (e) {
        debugPrint('[DIAGNOSTIC] Login attempt failed for $endpoint: $e');
        continue;
      }
    }
    return false;
  }

  /// Fetch user profile details (authenticated user ID and shop details)
  static Future<Map<String, dynamic>> fetchUserProfile() async {
    await ensureAuthenticated();
    final uri = Uri.parse('$_baseUrl/users/me');
    debugPrint('[DIAGNOSTIC] GET $uri');
    try {
      var response = await http.get(uri, headers: _getHeaders()).timeout(
        const Duration(seconds: 15),
      );

      if (response.statusCode == 401) {
        debugPrint('[Auth Guard] 401 received on profile fetch. Re-authenticating...');
        _token = null;
        if (await ensureAuthenticated()) {
          response = await http.get(uri, headers: _getHeaders()).timeout(const Duration(seconds: 15));
        }
      }

      debugPrint('[DIAGNOSTIC] GET $uri -> Status: ${response.statusCode}');
      if (response.statusCode == 200) {
        final profile = jsonDecode(response.body) as Map<String, dynamic>;
        debugPrint('[DIAGNOSTIC] AUTH USER ID: ${profile['id']} | Shop: ${profile['shop_name']}');
        return profile;
      }
      return {};
    } catch (e) {
      debugPrint('[DIAGNOSTIC] Profile fetch exception: $e');
      return {};
    }
  }

  /// Fetch complete Dashboard Summary metrics (Sales, Bills, Inventory counts, Khata Outstanding)
  static Future<Map<String, dynamic>> fetchDashboardSummary() async {
    await ensureAuthenticated();
    final uri = Uri.parse('$_baseUrl/dashboard/summary');
    debugPrint('[DIAGNOSTIC] REQUEST URL: GET $uri');
    final stopwatch = Stopwatch()..start();

    try {
      var response = await http.get(uri, headers: _getHeaders()).timeout(
        const Duration(seconds: 8),
      );

      if (response.statusCode == 401) {
        debugPrint('[Auth Guard] 401 received on dashboard summary request. Re-authenticating...');
        _token = null;
        if (await ensureAuthenticated()) {
          response = await http.get(uri, headers: _getHeaders()).timeout(const Duration(seconds: 8));
        }
      }

      stopwatch.stop();
      debugPrint('[DIAGNOSTIC] HTTP STATUS: ${response.statusCode} (Elapsed: ${stopwatch.elapsedMilliseconds}ms)');

      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        debugPrint('[DIAGNOSTIC] DASHBOARD SUMMARY LOADED: $decoded');
        return decoded;
      } else {
        throw Exception('Failed to load dashboard summary (HTTP ${response.statusCode})');
      }
    } catch (e) {
      stopwatch.stop();
      debugPrint('[DIAGNOSTIC] Dashboard summary exception: $e');
      rethrow;
    }
  }

  /// Fetch lightweight SQL-aggregated Inventory Health Dashboard summary metrics
  static Future<Map<String, dynamic>> fetchInventorySummary() async {
    await ensureAuthenticated();
    final uri = Uri.parse('$_baseUrl/inventory/summary');
    debugPrint('[DIAGNOSTIC] REQUEST URL: GET $uri');
    final stopwatch = Stopwatch()..start();

    try {
      var response = await http.get(uri, headers: _getHeaders()).timeout(
        const Duration(seconds: 15),
      );

      if (response.statusCode == 401) {
        debugPrint('[Auth Guard] 401 received on summary request. Re-authenticating...');
        _token = null;
        if (await ensureAuthenticated()) {
          response = await http.get(uri, headers: _getHeaders()).timeout(const Duration(seconds: 15));
        }
      }

      stopwatch.stop();
      debugPrint('[DIAGNOSTIC] HTTP STATUS: ${response.statusCode} (Elapsed: ${stopwatch.elapsedMilliseconds}ms)');

      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        debugPrint('[DIAGNOSTIC] DASHBOARD SUMMARY LOADED: $decoded');
        return decoded;
      } else {
        throw Exception('Failed to load inventory dashboard summary (HTTP ${response.statusCode})');
      }
    } catch (e) {
      stopwatch.stop();
      debugPrint('[DIAGNOSTIC] Inventory summary exception: $e');
      rethrow;
    }
  }

  /// Retrieve real-time inventory intelligence & valuation summary from backend
  static Future<Map<String, dynamic>> fetchInventoryIntelligence() async {
    await ensureAuthenticated();
    final uri = Uri.parse('$_baseUrl/inventory/intelligence');
    debugPrint('[DIAGNOSTIC] REQUEST URL: GET $uri');
    final stopwatch = Stopwatch()..start();

    try {
      var response = await http.get(uri, headers: _getHeaders()).timeout(
        const Duration(seconds: 15),
      );

      if (response.statusCode == 401) {
        debugPrint('[Auth Guard] 401 received on intelligence request. Re-authenticating...');
        _token = null;
        if (await ensureAuthenticated()) {
          response = await http.get(uri, headers: _getHeaders()).timeout(const Duration(seconds: 15));
        }
      }

      stopwatch.stop();
      debugPrint('[DIAGNOSTIC] HTTP STATUS: ${response.statusCode} (Elapsed: ${stopwatch.elapsedMilliseconds}ms)');

      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        final total = decoded['total_products'] ?? (decoded['summary'] != null ? decoded['summary']['total_products'] : null) ?? 0;
        final stockVal = decoded['total_stock_value'] ?? (decoded['summary'] != null ? decoded['summary']['total_stock_value'] : null) ?? 0.0;

        debugPrint('[DIAGNOSTIC] INTELLIGENCE RAW RESPONSE SUMMARY -> total_products: $total, total_stock_value: Rs.$stockVal');
        return decoded;
      } else {
        debugPrint('[DIAGNOSTIC] Intelligence request failed with HTTP ${response.statusCode}: ${response.body}');
        throw Exception('Failed to load inventory summary (HTTP ${response.statusCode})');
      }
    } catch (e) {
      stopwatch.stop();
      debugPrint('[DIAGNOSTIC] Intelligence fetch exception after ${stopwatch.elapsedMilliseconds}ms: $e');
      rethrow;
    }
  }

  /// Fetch paginated inventory stock list response
  static Future<Map<String, dynamic>> fetchProductsResponse({
    int page = 1,
    int limit = 50,
    String? search,
    String? filter,
    String? sortBy,
  }) async {
    await ensureAuthenticated();
    final queryParams = <String, String>{
      'page': page.toString(),
      'limit': limit.toString(),
      if (search != null && search.trim().isNotEmpty) 'search': search.trim(),
      if (filter != null && filter.trim().isNotEmpty) 'filter': filter.trim(),
      if (sortBy != null && sortBy.trim().isNotEmpty) 'sort_by': sortBy.trim(),
    };

    final uri = Uri.parse('$_baseUrl/products').replace(queryParameters: queryParams);
    debugPrint('[DIAGNOSTIC] REQUEST URL: GET $uri');
    final stopwatch = Stopwatch()..start();

    try {
      var response = await http.get(uri, headers: _getHeaders()).timeout(
        const Duration(seconds: 15),
      );

      if (response.statusCode == 401) {
        debugPrint('[Auth Guard] 401 received on product list request. Re-authenticating...');
        _token = null;
        if (await ensureAuthenticated()) {
          response = await http.get(uri, headers: _getHeaders()).timeout(const Duration(seconds: 15));
        }
      }

      stopwatch.stop();
      debugPrint('[DIAGNOSTIC] HTTP STATUS: ${response.statusCode} (Elapsed: ${stopwatch.elapsedMilliseconds}ms)');

      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body);
        if (decoded is List) {
          debugPrint('[DIAGNOSTIC] RAW RESPONSE COUNT: ${decoded.length}');
          return {
            'items': decoded,
            'total': decoded.length,
            'page': page,
            'pages': 1,
          };
        } else if (decoded is Map && decoded.containsKey('items')) {
          final items = decoded['items'] as List<dynamic>;
          final total = decoded['total'] ?? items.length;
          final pages = decoded['pages'] ?? 1;
          debugPrint('[DIAGNOSTIC] RAW RESPONSE COUNT: ${items.length} items on page $page, TOTAL DB COUNT: $total');
          return {
            'items': items,
            'total': total,
            'page': page,
            'pages': pages,
          };
        }
        return {'items': [], 'total': 0, 'page': page, 'pages': 1};
      } else {
        debugPrint('[DIAGNOSTIC] Product list request failed with HTTP ${response.statusCode}: ${response.body}');
        throw Exception('Failed to load products (HTTP ${response.statusCode})');
      }
    } catch (e) {
      stopwatch.stop();
      debugPrint('[DIAGNOSTIC] Products fetch exception: $e');
      rethrow;
    }
  }

  /// Retrieve full detail specification for a single medicine item
  static Future<Map<String, dynamic>> fetchProductDetails(int productId) async {
    await ensureAuthenticated();
    final uri = Uri.parse('$_baseUrl/products/$productId');
    debugPrint('[DIAGNOSTIC] REQUEST URL: GET $uri');
    final stopwatch = Stopwatch()..start();

    try {
      var response = await http.get(uri, headers: _getHeaders()).timeout(
        const Duration(seconds: 4),
      );

      if (response.statusCode == 401) {
        _token = null;
        if (await ensureAuthenticated()) {
          response = await http.get(uri, headers: _getHeaders()).timeout(const Duration(seconds: 4));
        }
      }

      stopwatch.stop();
      debugPrint('[DIAGNOSTIC] HTTP STATUS: ${response.statusCode} (Elapsed: ${stopwatch.elapsedMilliseconds}ms)');

      if (response.statusCode == 200) {
        return jsonDecode(response.body) as Map<String, dynamic>;
      }
      return {};
    } catch (e) {
      stopwatch.stop();
      debugPrint('[DIAGNOSTIC] fetchProductDetails exception: $e');
      return {};
    }
  }

  /// Autocomplete search for POS billing using GIN trigram indexed endpoint
  static Future<List<dynamic>> searchBillingProducts(String query, {int limit = 15}) async {
    await ensureAuthenticated();
    final cleanQ = query.trim();
    if (cleanQ.isEmpty) return [];

    final uri = Uri.parse('$_baseUrl/billing/search-products').replace(queryParameters: {
      'query': cleanQ,
      'limit': limit.toString(),
    });

    debugPrint('[DIAGNOSTIC] REQUEST URL: GET $uri');
    final stopwatch = Stopwatch()..start();

    try {
      var response = await http.get(uri, headers: _getHeaders()).timeout(
        const Duration(seconds: 5),
      );

      if (response.statusCode == 401) {
        _token = null;
        if (await ensureAuthenticated()) {
          response = await http.get(uri, headers: _getHeaders()).timeout(const Duration(seconds: 5));
        }
      }

      stopwatch.stop();
      debugPrint('[DIAGNOSTIC] HTTP STATUS: ${response.statusCode} (${stopwatch.elapsedMilliseconds}ms)');

      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body);
        if (decoded is List) {
          debugPrint('[DIAGNOSTIC] BILLING SEARCH PARSED COUNT: ${decoded.length} for query "$cleanQ"');
          return decoded;
        }
      }
      return [];
    } catch (e) {
      stopwatch.stop();
      debugPrint('[DIAGNOSTIC] Billing search exception: $e');
      return [];
    }
  }

  /// Legacy wrapper returning product items list
  static Future<List<dynamic>> fetchProducts({
    int page = 1,
    int limit = 50,
    String? search,
    String? filter,
    String? sortBy,
  }) async {
    final res = await fetchProductsResponse(page: page, limit: limit, search: search, filter: filter, sortBy: sortBy);
    return res['items'] as List<dynamic>;
  }

  /// Submit retail sale bill (Atomic Checkout with Idempotency)
  static Future<Map<String, dynamic>> createSale(Map<String, dynamic> payload) async {
    await ensureAuthenticated();
    final headers = _getHeaders();
    if (payload.containsKey('idempotency_key') && payload['idempotency_key'] != null) {
      headers['X-Idempotency-Key'] = payload['idempotency_key'].toString();
    }
    final response = await http.post(
      Uri.parse('$_baseUrl/sales'),
      headers: headers,
      body: jsonEncode(payload),
    );

    if (response.statusCode == 201 || response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else {
      final decoded = jsonDecode(response.body);
      throw Exception(decoded['detail'] ?? 'Failed to complete sale transaction');
    }
  }

  /// Submit retail sale bill return (One-tap Patient Return)
  static Future<Map<String, dynamic>> createSaleReturn(Map<String, dynamic> payload) async {
    await ensureAuthenticated();
    final response = await http.post(
      Uri.parse('$_baseUrl/billing/returns'),
      headers: _getHeaders(),
      body: jsonEncode(payload),
    );

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else {
      throw Exception(jsonDecode(response.body)['detail'] ?? 'Failed to submit sale return');
    }
  }

  /// Submit wholesale purchase invoice
  static Future<Map<String, dynamic>> createPurchase(Map<String, dynamic> payload) async {
    await ensureAuthenticated();
    final response = await http.post(
      Uri.parse('$_baseUrl/purchases'),
      headers: _getHeaders(),
      body: jsonEncode(payload),
    );

    if (response.statusCode == 201) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else {
      throw Exception(jsonDecode(response.body)['detail'] ?? 'Failed to register purchase');
    }
  }

  /// Submit wholesale purchase returns
  static Future<Map<String, dynamic>> createPurchaseReturn(Map<String, dynamic> payload) async {
    await ensureAuthenticated();
    final response = await http.post(
      Uri.parse('$_baseUrl/purchases/returns'),
      headers: _getHeaders(),
      body: jsonEncode(payload),
    );

    if (response.statusCode == 201) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else {
      throw Exception(jsonDecode(response.body)['detail'] ?? 'Failed to submit purchase return');
    }
  }

  /// Log customer collection payment (Khata ledger payment)
  static Future<Map<String, dynamic>> createCustomerPayment(int customerId, Map<String, dynamic> payload) async {
    await ensureAuthenticated();
    final response = await http.post(
      Uri.parse('$_baseUrl/customers/$customerId/payments'),
      headers: _getHeaders(),
      body: jsonEncode(payload),
    );

    if (response.statusCode == 201) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else {
      throw Exception(jsonDecode(response.body)['detail'] ?? 'Failed to submit payment');
    }
  }

  /// Retrieve chronological running customer credit ledger
  static Future<Map<String, dynamic>> fetchCustomerLedger(int customerId) async {
    await ensureAuthenticated();
    final response = await http.get(
      Uri.parse('$_baseUrl/customers/$customerId/ledger'),
      headers: _getHeaders(),
    );

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else {
      throw Exception('Failed to load customer ledger');
    }
  }

  /// Search original sales bills by medicine name or bill number
  static Future<List<dynamic>> searchSalesByMedicine(String query) async {
    await ensureAuthenticated();
    final uri = Uri.parse('$_baseUrl/api/sales/search-by-medicine?query=${Uri.encodeComponent(query)}');
    final response = await http.get(uri, headers: _getHeaders());
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as List<dynamic>;
    } else {
      throw Exception('Failed to search sales by medicine');
    }
  }

  /// Process item return and restore database inventory stock
  static Future<Map<String, dynamic>> processSaleReturn({
    required int saleId,
    required int saleItemId,
    required int returnQuantity,
    String? reason,
  }) async {
    await ensureAuthenticated();
    final uri = Uri.parse('$_baseUrl/api/sales/returns');
    final response = await http.post(
      uri,
      headers: _getHeaders(),
      body: jsonEncode({
        'sale_id': saleId,
        'reason': reason ?? 'Customer Return',
        'items': [
          {
            'sale_item_id': saleItemId,
            'return_quantity': returnQuantity,
          }
        ]
      }),
    );

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else {
      final err = jsonDecode(response.body);
      throw Exception(err['detail'] ?? 'Failed to process return');
    }
  }

  /// Fetch today's returned items and refund summary
  static Future<Map<String, dynamic>> fetchTodayReturns() async {
    await ensureAuthenticated();
    final uri = Uri.parse('$_baseUrl/api/sales/returns/today');
    final response = await http.get(uri, headers: _getHeaders());
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else {
      throw Exception('Failed to load today returns summary');
    }
  }

  /// Fetch filterable returns history
  static Future<List<dynamic>> fetchReturnsHistory({String? query}) async {
    await ensureAuthenticated();
    var url = '$_baseUrl/api/sales/returns';
    if (query != null && query.isNotEmpty) {
      url += '?search=${Uri.encodeComponent(query)}';
    }
    final response = await http.get(Uri.parse(url), headers: _getHeaders());
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as List<dynamic>;
    } else {
      throw Exception('Failed to load returns history');
    }
  }

  /// Check online for new published mobile app version
  static Future<Map<String, dynamic>> checkAppVersion() async {
    try {
      final uri = Uri.parse('$_baseUrl/app/version');
      final response = await http.get(uri, headers: {
        'User-Agent': 'DawaiFlowMobile/1.0',
        'Accept': 'application/json',
      }).timeout(const Duration(seconds: 4));

      if (response.statusCode == 200) {
        return jsonDecode(response.body) as Map<String, dynamic>;
      }
      return {};
    } catch (e) {
      debugPrint('[ApiService] Version check error: $e');
      return {};
    }
  }
}
