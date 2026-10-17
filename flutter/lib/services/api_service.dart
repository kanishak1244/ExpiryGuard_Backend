import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

class ApiService {
  static String _baseUrl = 'https://api.dawaiflow.com';
  static String? _token;
  static String? _savedToken;
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
    _savedToken = token;
    debugPrint('[DIAGNOSTIC] setToken: Token updated (Length: ${token.length})');
  }

  static String? getToken() {
    return _token ?? _savedToken;
  }

  /// Dynamically probes available backend server addresses to find the fastest responding host.
  /// Uses caching and primary host prioritization to eliminate latency on mobile networks.
  static Future<String> discoverWorkingBaseUrl() async {
    if (kIsWeb || _isDiscoveringBaseUrl) return _baseUrl;

    // Return cached base URL if verified within the last 10 minutes
    if (_lastDiscoveryTime != null &&
        DateTime.now().difference(_lastDiscoveryTime!).inSeconds < 600) {
      return _baseUrl;
    }

    _isDiscoveringBaseUrl = true;

    // Check currently configured _baseUrl with 5s timeout for mobile networks
    try {
      final res = await http.get(
        Uri.parse('$_baseUrl/health'),
        headers: {'User-Agent': 'DawaiFlowMobile/1.0'},
      ).timeout(const Duration(milliseconds: 5000));
      if (res.statusCode == 200) {
        _lastDiscoveryTime = DateTime.now();
        _isDiscoveringBaseUrl = false;
        return _baseUrl;
      }
    } catch (_) {}

    // In release mode or if primary host is production domain, retain primary host
    if (kReleaseMode || _baseUrl == 'https://api.dawaiflow.com') {
      _lastDiscoveryTime = DateTime.now();
      _isDiscoveringBaseUrl = false;
      return _baseUrl;
    }

    debugPrint('[Host Discovery] Debug mode: Probing candidate backend URLs...');

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

    if (_token == null && _savedToken != null && _savedToken!.isNotEmpty) {
      _token = _savedToken;
    }

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
    final tokenToUse = _token ?? _savedToken;
    return {
      'Content-Type': 'application/json',
      'User-Agent': 'DawaiFlowMobile/1.0',
      if (tokenToUse != null && tokenToUse.isNotEmpty)
        'Authorization': 'Bearer $tokenToUse',
    };
  }

  /// Centralized robust HTTP GET executor.
  /// Immediately fails on HTTP 404 without retrying.
  /// Performs single bounded retry only on 401 token refresh or transient 502-504 / network drops.
  static Future<http.Response> _safeGet(
    Uri uri, {
    Duration timeout = const Duration(seconds: 10),
  }) async {
    await ensureAuthenticated();

    int attempts = 0;
    while (attempts < 2) {
      attempts++;
      try {
        final response = await http.get(uri, headers: _getHeaders()).timeout(timeout);

        // HTTP 404 is NOT a transient failure — return immediately without retrying
        if (response.statusCode == 404) {
          debugPrint('[ApiService] HTTP 404 Not Found for GET $uri. Failing immediately without retry.');
          return response;
        }

        if (response.statusCode == 401 && attempts == 1) {
          debugPrint('[ApiService] 401 received for GET $uri (attempt 1). Retrying once with saved token...');
          if (_savedToken != null && _savedToken!.isNotEmpty) {
            _token = _savedToken;
          }
          await Future.delayed(const Duration(milliseconds: 500));
          continue;
        }

        if ((response.statusCode >= 502 && response.statusCode <= 504) && attempts == 1) {
          debugPrint('[ApiService] Gateway error ${response.statusCode} for GET $uri. Retrying in 600ms...');
          await Future.delayed(const Duration(milliseconds: 600));
          continue;
        }

        return response;
      } catch (e) {
        if (attempts == 1) {
          debugPrint('[ApiService] Transient network exception ($e) on GET $uri. Retrying in 500ms...');
          await Future.delayed(const Duration(milliseconds: 500));
          continue;
        }
        rethrow;
      }
    }
    throw Exception('Network request failed for $uri');
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
      if (base.isEmpty) continue;
      if (kReleaseMode && base != 'https://api.dawaiflow.com' && base != _baseUrl) continue;
      final endpoint = '$base/login';
      try {
        debugPrint('[DIAGNOSTIC] Attempting POST $endpoint');
        final response = await http.post(
          Uri.parse(endpoint),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'email': email, 'password': password}),
        ).timeout(const Duration(seconds: 5));

        debugPrint('[DIAGNOSTIC] POST $endpoint -> HTTP Status: ${response.statusCode}');

        if (response.statusCode == 200) {
          final data = jsonDecode(response.body);
          _token = data['access_token'];
          _savedToken = _token;
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
    final uri = Uri.parse('$_baseUrl/users/me');
    debugPrint('[DIAGNOSTIC] GET $uri');
    try {
      final response = await _safeGet(uri, timeout: const Duration(seconds: 15));
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

  /// Fetch complete Dashboard Summary metrics using confirmed production GET /app/bootstrap endpoint with fallback to /dashboard/summary
  static Future<Map<String, dynamic>> fetchDashboardSummary() async {
    final uriBootstrap = Uri.parse('$_baseUrl/app/bootstrap');
    debugPrint('[DIAGNOSTIC] REQUEST URL: GET $uriBootstrap');
    final stopwatch = Stopwatch()..start();

    try {
      final response = await _safeGet(uriBootstrap, timeout: const Duration(seconds: 10));
      stopwatch.stop();
      debugPrint('[DIAGNOSTIC] HTTP STATUS: ${response.statusCode} (Elapsed: ${stopwatch.elapsedMilliseconds}ms)');

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;

        final dashSummary = data['dashboard_summary'] as Map<String, dynamic>? ?? {};
        final invSummary = data['inventory_summary'] as Map<String, dynamic>? ?? {};
        final khataSummary = data['khata_summary'] as Map<String, dynamic>? ?? {};

        final merged = <String, dynamic>{
          'today_business': {
            'sales': (dashSummary['today_revenue'] ?? 0.0).toDouble(),
            'bills': dashSummary['today_sales_count'] ?? 0,
            'today_profit': (dashSummary['today_profit'] ?? 0.0).toDouble(),
          },
          'today_revenue': dashSummary['today_revenue'] ?? 0.0,
          'today_sales_count': dashSummary['today_sales_count'] ?? 0,
          'expired_count': dashSummary['expired_count'] ?? invSummary['expired_count'] ?? 0,
          'expiring_soon_count': dashSummary['expiring_soon_count'] ?? invSummary['expiring_soon_count'] ?? 0,
          'low_stock_count': invSummary['low_stock_count'] ?? 0,
          'customer_outstanding': khataSummary['total_receivables'] ?? dashSummary['pending_payments_total'] ?? 0.0,
          'total_products': invSummary['total_products'] ?? dashSummary['total_products'] ?? 0,
          'needs_attention': {
            'expired_count': dashSummary['expired_count'] ?? invSummary['expired_count'] ?? 0,
            'expiring_soon_count': dashSummary['expiring_soon_count'] ?? invSummary['expiring_soon_count'] ?? 0,
            'low_stock_count': invSummary['low_stock_count'] ?? 0,
            'customer_outstanding': khataSummary['total_receivables'] ?? 0.0,
          }
        };

        debugPrint('[DIAGNOSTIC] DASHBOARD SUMMARY LOADED FROM /app/bootstrap: $merged');
        return merged;
      }
    } catch (e) {
      debugPrint('[DIAGNOSTIC] /app/bootstrap failed: $e. Retrying /dashboard/summary...');
    }

    final uriSummary = Uri.parse('$_baseUrl/dashboard/summary');
    try {
      final response = await _safeGet(uriSummary, timeout: const Duration(seconds: 10));
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return decoded;
      }
      throw Exception('Failed to load dashboard summary (HTTP ${response.statusCode})');
    } catch (e) {
      stopwatch.stop();
      debugPrint('[DIAGNOSTIC] Dashboard summary exception: $e');
      rethrow;
    }
  }

  /// Fetch lightweight SQL-aggregated Inventory Health Dashboard summary metrics
  static Future<Map<String, dynamic>> fetchInventorySummary() async {
    final uri = Uri.parse('$_baseUrl/inventory/summary');
    debugPrint('[DIAGNOSTIC] REQUEST URL: GET $uri');
    final stopwatch = Stopwatch()..start();

    try {
      final response = await _safeGet(uri, timeout: const Duration(seconds: 15));
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
    final uri = Uri.parse('$_baseUrl/inventory/intelligence');
    debugPrint('[DIAGNOSTIC] REQUEST URL: GET $uri');
    final stopwatch = Stopwatch()..start();

    try {
      final response = await _safeGet(uri, timeout: const Duration(seconds: 15));
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
      final response = await _safeGet(uri, timeout: const Duration(seconds: 15));
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
    final uri = Uri.parse('$_baseUrl/products/$productId');
    debugPrint('[DIAGNOSTIC] REQUEST URL: GET $uri');
    final stopwatch = Stopwatch()..start();

    try {
      final response = await _safeGet(uri, timeout: const Duration(seconds: 6));
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
    final cleanQ = query.trim();
    if (cleanQ.isEmpty) return [];

    final uri = Uri.parse('$_baseUrl/billing/search-products').replace(queryParameters: {
      'query': cleanQ,
      'limit': limit.toString(),
    });

    debugPrint('[DIAGNOSTIC] REQUEST URL: GET $uri');
    final stopwatch = Stopwatch()..start();

    try {
      final response = await _safeGet(uri, timeout: const Duration(seconds: 6));
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
    ).timeout(const Duration(seconds: 15));

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
    ).timeout(const Duration(seconds: 15));

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
    ).timeout(const Duration(seconds: 15));

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
    ).timeout(const Duration(seconds: 15));

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
    ).timeout(const Duration(seconds: 15));

    if (response.statusCode == 201) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else {
      throw Exception(jsonDecode(response.body)['detail'] ?? 'Failed to submit payment');
    }
  }

  /// Retrieve chronological running customer credit ledger
  static Future<Map<String, dynamic>> fetchCustomerLedger(int customerId) async {
    final uri = Uri.parse('$_baseUrl/customers/$customerId/ledger');
    final response = await _safeGet(uri, timeout: const Duration(seconds: 10));

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else {
      throw Exception('Failed to load customer ledger');
    }
  }

  /// Search original sales bills by medicine name or bill number
  static Future<List<dynamic>> searchSalesByMedicine(String query) async {
    final uri = Uri.parse('$_baseUrl/api/sales/search-by-medicine?query=${Uri.encodeComponent(query)}');
    final response = await _safeGet(uri, timeout: const Duration(seconds: 10));
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
    ).timeout(const Duration(seconds: 15));

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else {
      final err = jsonDecode(response.body);
      throw Exception(err['detail'] ?? 'Failed to process return');
    }
  }

  /// Fetch today's returned items and refund summary
  static Future<Map<String, dynamic>> fetchTodayReturns() async {
    final uri = Uri.parse('$_baseUrl/api/sales/returns/today');
    final response = await _safeGet(uri, timeout: const Duration(seconds: 10));
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else {
      throw Exception('Failed to load today returns summary');
    }
  }

  /// Fetch filterable returns history
  static Future<List<dynamic>> fetchReturnsHistory({String? query}) async {
    var url = '$_baseUrl/api/sales/returns';
    if (query != null && query.isNotEmpty) {
      url += '?search=${Uri.encodeComponent(query)}';
    }
    final response = await _safeGet(Uri.parse(url), timeout: const Duration(seconds: 10));
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

  /// Scans multi-item medicine strips/boxes using backend AI vision endpoint
  static Future<Map<String, dynamic>> scanMultiItem(List<int> imageBytes, {String filename = 'scan.jpg'}) async {
    await ensureAuthenticated();
    final uri = Uri.parse('$_baseUrl/scan-multi-item');
    
    final tokenToUse = _token ?? _savedToken;
    final headers = <String, String>{
      'User-Agent': 'DawaiFlowMobile/1.0',
      if (tokenToUse != null && tokenToUse.isNotEmpty)
        'Authorization': 'Bearer $tokenToUse',
    };

    int attempts = 0;
    while (attempts < 2) {
      attempts++;
      try {
        final request = http.MultipartRequest('POST', uri);
        request.headers.addAll(headers);
        request.files.add(http.MultipartFile.fromBytes(
          'file',
          imageBytes,
          filename: filename,
        ));

        final streamedResponse = await request.send().timeout(const Duration(seconds: 30));
        final response = await http.Response.fromStream(streamedResponse);

        if (response.statusCode == 401 && attempts == 1) {
          debugPrint('[ApiService] 401 received on scanMultiItem. Re-authenticating...');
          _token = null;
          if (await ensureAuthenticated()) {
            final freshToken = _token ?? _savedToken;
            if (freshToken != null && freshToken.isNotEmpty) {
              headers['Authorization'] = 'Bearer $freshToken';
            }
            continue;
          }
        }

        if (response.statusCode == 200) {
          return jsonDecode(response.body) as Map<String, dynamic>;
        } else {
          final decoded = jsonDecode(response.body);
          final detail = decoded is Map ? (decoded['detail'] ?? 'Multi-item scan failed') : 'Multi-item scan failed';
          throw Exception(detail);
        }
      } catch (e) {
        if (attempts == 1 && e is! Exception) {
          continue;
        }
        rethrow;
      }
    }
    throw Exception('Multi-item scan failed after retry');
  }
}
