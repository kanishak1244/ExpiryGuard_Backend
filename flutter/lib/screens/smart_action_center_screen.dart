import 'package:flutter/material.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import '../widgets/status_badge.dart';
import '../services/api_service.dart';

class SmartActionCenterScreen extends StatefulWidget {
  final String filterKey;
  final String categoryTitle;

  const SmartActionCenterScreen({
    super.key,
    required this.filterKey,
    required this.categoryTitle,
  });

  @override
  State<SmartActionCenterScreen> createState() => _SmartActionCenterScreenState();
}

class _SmartActionCenterScreenState extends State<SmartActionCenterScreen> {
  final List<Map<String, dynamic>> _items = [];
  bool _isLoading = true;
  String? _errorMessage;

  int _currentPage = 1;
  int _totalPages = 1;
  int _totalCount = 0;
  String _searchQuery = '';
  final TextEditingController _searchController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
    _loadAttentionItems();
  }

  @override
  void dispose() {
    _scrollController.dispose();
    _searchController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrollController.position.pixels >= _scrollController.position.maxScrollExtent - 300) {
      if (_currentPage < _totalPages && !_isLoading) {
        _loadMoreItems();
      }
    }
  }

  Future<void> _loadAttentionItems() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
      _currentPage = 1;
    });

    try {
      final res = await ApiService.fetchProductsResponse(
        page: 1,
        limit: 50,
        filter: widget.filterKey,
        search: _searchQuery,
      );

      final List<dynamic> rawItems = res['items'] as List<dynamic>;
      final int total = res['total'] ?? rawItems.length;
      final int pages = res['pages'] ?? 1;

      final parsed = <Map<String, dynamic>>[];
      for (var item in rawItems) {
        parsed.add({
          'id': item['id'],
          'name': item['product_name'] ?? 'Unnamed Product',
          'brand': item['brand'] ?? '',
          'category': item['category'] ?? 'General',
          'composition': item['composition'] ?? '',
          'batch': item['batch_number'] ?? 'N/A',
          'quantity': item['quantity'] ?? 0,
          'mrp': (item['unit_price'] ?? 0.0) as num,
          'expiry': item['expiry_date'] ?? 'N/A',
          'days_left': item['days_remaining'] ?? 0,
          'purchase_price': (item['purchase_price'] ?? 0.0) as num,
          'hsn_code': item['hsn_code'] ?? '3004',
        });
      }

      if (!mounted) return;

      setState(() {
        _items.clear();
        _items.addAll(parsed);
        _totalCount = total;
        _totalPages = pages;
        _currentPage = 1;
        _isLoading = false;
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoading = false;
          _errorMessage = e.toString();
        });
      }
    }
  }

  Future<void> _loadMoreItems() async {
    if (_currentPage >= _totalPages) return;

    final nextPage = _currentPage + 1;
    try {
      final res = await ApiService.fetchProductsResponse(
        page: nextPage,
        limit: 50,
        filter: widget.filterKey,
        search: _searchQuery,
      );

      final List<dynamic> rawItems = res['items'] as List<dynamic>;

      final parsed = <Map<String, dynamic>>[];
      for (var item in rawItems) {
        parsed.add({
          'id': item['id'],
          'name': item['product_name'] ?? 'Unnamed Product',
          'brand': item['brand'] ?? '',
          'category': item['category'] ?? 'General',
          'composition': item['composition'] ?? '',
          'batch': item['batch_number'] ?? 'N/A',
          'quantity': item['quantity'] ?? 0,
          'mrp': (item['unit_price'] ?? 0.0) as num,
          'expiry': item['expiry_date'] ?? 'N/A',
          'days_left': item['days_remaining'] ?? 0,
          'purchase_price': (item['purchase_price'] ?? 0.0) as num,
          'hsn_code': item['hsn_code'] ?? '3004',
        });
      }

      if (!mounted) return;

      setState(() {
        _items.addAll(parsed);
        _currentPage = nextPage;
      });
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surfaceBg,
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Smart Action Center', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            Text(widget.categoryTitle, style: const TextStyle(fontSize: 12, color: Colors.white70)),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_rounded),
            onPressed: _loadAttentionItems,
          ),
        ],
      ),
      body: Column(
        children: [
          // Filter Summary Header
          Container(
            padding: const EdgeInsets.all(AppSpacing.md),
            color: Colors.white,
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: AppColors.statusWarningBg,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Icon(Icons.bolt_rounded, color: AppColors.statusWarningText),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '${widget.categoryTitle} (${_isLoading ? '...' : _totalCount})',
                        style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15, color: AppColors.textPrimary),
                      ),
                      const SizedBox(height: 2),
                      const Text('Live backend attention items requiring review', style: TextStyle(fontSize: 12, color: AppColors.textMuted)),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const Divider(height: 1),

          // Search Filter Bar
          Padding(
            padding: const EdgeInsets.all(AppSpacing.md),
            child: TextField(
              controller: _searchController,
              decoration: InputDecoration(
                hintText: 'Search within ${widget.categoryTitle}...',
                prefixIcon: const Icon(Icons.search, size: 20),
                suffixIcon: _searchQuery.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear, size: 18),
                        onPressed: () {
                          _searchController.clear();
                          setState(() => _searchQuery = '');
                          _loadAttentionItems();
                        },
                      )
                    : null,
                filled: true,
                fillColor: Colors.white,
                contentPadding: const EdgeInsets.symmetric(vertical: 10, horizontal: 16),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: const BorderSide(color: AppColors.border)),
                enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: const BorderSide(color: AppColors.border)),
              ),
              onSubmitted: (val) {
                setState(() => _searchQuery = val.trim());
                _loadAttentionItems();
              },
            ),
          ),

          // Content List / Empty State / Loading
          Expanded(
            child: _isLoading
                ? const Center(child: CircularProgressIndicator())
                : _errorMessage != null
                    ? Center(
                        child: Padding(
                          padding: const EdgeInsets.all(24.0),
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              const Icon(Icons.error_outline_rounded, color: AppColors.statusDanger, size: 48),
                              const SizedBox(height: 12),
                              Text('Failed to load ${widget.categoryTitle}', style: const TextStyle(fontWeight: FontWeight.bold)),
                              const SizedBox(height: 6),
                              Text(_errorMessage!, textAlign: TextAlign.center, style: const TextStyle(fontSize: 12, color: AppColors.textMuted)),
                              const SizedBox(height: 16),
                              ElevatedButton(onPressed: _loadAttentionItems, child: const Text('Retry Connection')),
                            ],
                          ),
                        ),
                      )
                    : _items.isEmpty
                        ? Center(
                            child: Padding(
                              padding: const EdgeInsets.all(32.0),
                              child: Column(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  Container(
                                    padding: const EdgeInsets.all(16),
                                    decoration: BoxDecoration(
                                      color: AppColors.statusSafeBg,
                                      shape: BoxShape.circle,
                                    ),
                                    child: const Icon(Icons.check_circle_outline_rounded, color: AppColors.statusSafeText, size: 56),
                                  ),
                                  const SizedBox(height: 16),
                                  const Text('All Caught Up!', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppColors.textPrimary)),
                                  const SizedBox(height: 8),
                                  Text(
                                    'No matching items found in ${widget.categoryTitle}. Your inventory health is optimal.',
                                    textAlign: TextAlign.center,
                                    style: const TextStyle(color: AppColors.textMuted, fontSize: 13),
                                  ),
                                  const SizedBox(height: 20),
                                  OutlinedButton.icon(
                                    icon: const Icon(Icons.refresh),
                                    label: const Text('Refresh Data'),
                                    onPressed: _loadAttentionItems,
                                  ),
                                ],
                              ),
                            ),
                          )
                        : RefreshIndicator(
                            onRefresh: _loadAttentionItems,
                            child: ListView.separated(
                              controller: _scrollController,
                              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: AppSpacing.sm),
                              itemCount: _items.length,
                              separatorBuilder: (context, index) => const SizedBox(height: AppSpacing.sm),
                              itemBuilder: (context, index) {
                                final med = _items[index];
                                final int daysLeft = med['days_left'] ?? 0;
                                final int qty = med['quantity'] ?? 0;

                                BadgeStatus status = BadgeStatus.safe;
                                String statusText = 'Safe';
                                if (daysLeft <= 0) {
                                  status = BadgeStatus.danger;
                                  statusText = 'Expired';
                                } else if (daysLeft <= 60) {
                                  status = BadgeStatus.warning;
                                  statusText = 'Expiring Soon ($daysLeft d)';
                                }
                                if (qty <= 10) {
                                  status = BadgeStatus.warning;
                                  statusText = 'Low Stock ($qty)';
                                }

                                return Card(
                                  elevation: 0,
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(12),
                                    side: const BorderSide(color: AppColors.border),
                                  ),
                                  child: Padding(
                                    padding: const EdgeInsets.all(14.0),
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Row(
                                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                          crossAxisAlignment: CrossAxisAlignment.start,
                                          children: [
                                            Expanded(
                                              child: Column(
                                                crossAxisAlignment: CrossAxisAlignment.start,
                                                children: [
                                                  Text(
                                                    med['name'],
                                                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15, color: AppColors.textPrimary),
                                                  ),
                                                  if ((med['brand'] as String).isNotEmpty)
                                                    Text(med['brand'], style: const TextStyle(fontSize: 12, color: AppColors.textMuted)),
                                                ],
                                              ),
                                            ),
                                            StatusBadge(label: statusText, status: status),
                                          ],
                                        ),
                                        const SizedBox(height: 10),
                                        Row(
                                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                          children: [
                                            Text('Batch: ${med['batch']}', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                                            Text('Stock: ${med['quantity']} units', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: qty <= 5 ? AppColors.statusDanger : AppColors.textPrimary)),
                                            Text('MRP: ₹${(med['mrp'] as num).toStringAsFixed(2)}', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.brandDeep)),
                                          ],
                                        ),
                                        const SizedBox(height: 6),
                                        Text('Expiry Date: ${med['expiry']}', style: const TextStyle(fontSize: 12, color: AppColors.textMuted)),
                                      ],
                                    ),
                                  ),
                                );
                              },
                            ),
                          ),
          ),
        ],
      ),
    );
  }
}
