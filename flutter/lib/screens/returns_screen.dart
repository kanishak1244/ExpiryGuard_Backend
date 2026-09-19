import 'package:flutter/material.dart';
import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../theme/app_spacing.dart';
import '../services/api_service.dart';

class ReturnsScreen extends StatefulWidget {
  const ReturnsScreen({super.key});

  @override
  State<ReturnsScreen> createState() => _ReturnsScreenState();
}

class _ReturnsScreenState extends State<ReturnsScreen> {
  bool _isLoading = true;
  String? _errorMessage;

  double _todayRefundTotal = 0.0;
  int _todayReturnCount = 0;
  int _todayTotalItemsReturned = 0;

  List<dynamic> _returnsHistory = [];
  String _searchQuery = '';

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final summary = await ApiService.fetchTodayReturns();
      final history = await ApiService.fetchReturnsHistory(query: _searchQuery);

      if (!mounted) return;

      setState(() {
        _todayRefundTotal = (summary['total_refund_amount'] ?? 0.0).toDouble();
        _todayReturnCount = (summary['total_returns_count'] ?? 0) as int;
        _todayTotalItemsReturned = (summary['total_items_returned'] ?? 0) as int;
        _returnsHistory = history;
        _isLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
        _errorMessage = e.toString();
      });
    }
  }

  void _openProcessReturnModal() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => const ProcessReturnBottomSheet(),
    ).then((ret) {
      if (ret == true) {
        _loadData();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surfaceBg,
      body: RefreshIndicator(
        onRefresh: _loadData,
        child: ListView(
          padding: const EdgeInsets.all(AppSpacing.md),
          children: [
            // Top Bar Action Header
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Sales Returns', style: AppTypography.heading2),
                    const Text('Track customer returns & manage refunds',
                        style: TextStyle(color: AppColors.textMuted, fontSize: 12)),
                  ],
                ),
                ElevatedButton.icon(
                  onPressed: _openProcessReturnModal,
                  icon: const Icon(Icons.add_rounded, size: 18),
                  label: const Text('Process Return'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.brandDeep,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.md),

            // Summary KPI Row
            Row(
              children: [
                Expanded(
                  child: _buildMetricCard(
                    'Today\'s Returns',
                    '₹${_todayRefundTotal.toStringAsFixed(2)}',
                    Icons.assignment_return_outlined,
                    AppColors.brandDeep,
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: _buildMetricCard(
                    'Total Bills Returned',
                    '$_todayReturnCount bills',
                    Icons.receipt_long_outlined,
                    AppColors.statusInfo,
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: _buildMetricCard(
                    'Items Quantity',
                    '$_todayTotalItemsReturned items',
                    Icons.inventory_2_outlined,
                    AppColors.statusWarning,
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.md),

            // Search Bar
            TextField(
              decoration: InputDecoration(
                hintText: 'Search returned medicine, bill #, customer...',
                prefixIcon: const Icon(Icons.search, color: AppColors.textMuted),
                filled: true,
                fillColor: Colors.white,
                contentPadding: const EdgeInsets.symmetric(vertical: 10),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(10),
                  borderSide: const BorderSide(color: AppColors.border),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(10),
                  borderSide: const BorderSide(color: AppColors.border),
                ),
              ),
              onChanged: (val) {
                _searchQuery = val;
                _loadData();
              },
            ),
            const SizedBox(height: AppSpacing.md),

            // Table / History View
            if (_isLoading)
              const Center(
                child: Padding(
                  padding: EdgeInsets.all(32.0),
                  child: CircularProgressIndicator(),
                ),
              )
            else if (_errorMessage != null)
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.red.shade50,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text('Error: $_errorMessage', style: TextStyle(color: Colors.red.shade700)),
              )
            else if (_returnsHistory.isEmpty)
              Container(
                padding: const EdgeInsets.all(32),
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: AppColors.border),
                ),
                child: const Column(
                  children: [
                    Icon(Icons.assignment_return_outlined, size: 48, color: AppColors.textMuted),
                    SizedBox(height: 12),
                    Text('No returned items found', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                    SizedBox(height: 4),
                    Text('Processed sales returns will appear here.', style: TextStyle(color: AppColors.textMuted, fontSize: 12)),
                  ],
                ),
              )
            else
              ListView.builder(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                itemCount: _returnsHistory.length,
                itemBuilder: (context, index) {
                  final item = _returnsHistory[index];
                  final medicineName = item['medicine_name'] ?? 'Item';
                  final batchNo = item['batch_number'] ?? 'N/A';
                  final saleId = item['sale_id'] ?? item['bill_number'] ?? '';
                  final customer = item['customer_name'] ?? 'Walk-in';
                  final returnQty = item['return_quantity'] ?? 0;
                  final refundAmount = item['refund_amount'] ?? 0.0;
                  final reason = item['reason'] ?? 'Customer Return';

                  return Card(
                    margin: const EdgeInsets.only(bottom: 8),
                    elevation: 0,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10),
                      side: const BorderSide(color: AppColors.border),
                    ),
                    child: Padding(
                      padding: const EdgeInsets.all(12.0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Expanded(
                                child: Text(
                                  medicineName,
                                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                              Text(
                                '- ₹${refundAmount.toStringAsFixed(2)}',
                                style: const TextStyle(
                                  fontWeight: FontWeight.bold,
                                  fontSize: 15,
                                  color: AppColors.statusDanger,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 4),
                          Row(
                            children: [
                              Text('Batch: $batchNo', style: const TextStyle(fontSize: 12, color: AppColors.textMuted)),
                              const SizedBox(width: 8),
                              const Text('•', style: TextStyle(color: AppColors.textMuted)),
                              const SizedBox(width: 8),
                              Text('Bill #$saleId', style: const TextStyle(fontSize: 12, color: AppColors.textMuted)),
                              const SizedBox(width: 8),
                              const Text('•', style: TextStyle(color: AppColors.textMuted)),
                              const SizedBox(width: 8),
                              Text(customer, style: const TextStyle(fontSize: 12, color: AppColors.textMuted)),
                            ],
                          ),
                          const Divider(height: 16),
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(
                                'Qty Returned: $returnQty unit(s)',
                                style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 12),
                              ),
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                decoration: BoxDecoration(
                                  color: AppColors.brandDeep.withOpacity(0.1),
                                  borderRadius: BorderRadius.circular(4),
                                ),
                                child: Text(
                                  reason,
                                  style: const TextStyle(fontSize: 11, color: AppColors.brandDeep, fontWeight: FontWeight.w500),
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  );
                },
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildMetricCard(String title, String value, IconData icon, Color color) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: const BorderSide(color: AppColors.border),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: color, size: 20),
            const SizedBox(height: 8),
            Text(value, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: AppColors.textPrimary)),
            const SizedBox(height: 2),
            Text(title, style: const TextStyle(fontSize: 11, color: AppColors.textMuted)),
          ],
        ),
      ),
    );
  }
}

/// 3-Step Process Return Bottom Sheet Modal
class ProcessReturnBottomSheet extends StatefulWidget {
  const ProcessReturnBottomSheet({super.key});

  @override
  State<ProcessReturnBottomSheet> createState() => _ProcessReturnBottomSheetState();
}

class _ProcessReturnBottomSheetState extends State<ProcessReturnBottomSheet> {
  int _step = 1; // 1: Search, 2: Select Item/Bill, 3: Confirm Quantity & Reason

  String _searchQuery = '';
  bool _isSearching = false;
  List<dynamic> _searchResults = [];
  String? _searchError;

  dynamic _selectedSale;
  dynamic _selectedItem;

  final TextEditingController _qtyController = TextEditingController(text: '1');
  final TextEditingController _reasonController = TextEditingController(text: 'Customer Return');
  bool _isSubmitting = false;
  String? _submitError;

  Future<void> _performSearch() async {
    if (_searchQuery.trim().isEmpty) return;
    setState(() {
      _isSearching = true;
      _searchError = null;
    });

    try {
      final results = await ApiService.searchSalesByMedicine(_searchQuery.trim());
      if (!mounted) return;
      setState(() {
        _searchResults = results;
        _isSearching = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isSearching = false;
        _searchError = e.toString();
      });
    }
  }

  void _selectSaleAndItem(dynamic sale, dynamic item) {
    final int maxReturnable = (item['quantity'] ?? 0) - (item['returned_quantity'] ?? 0);
    if (maxReturnable <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('This item has already been fully returned.')),
      );
      return;
    }

    setState(() {
      _selectedSale = sale;
      _selectedItem = item;
      _qtyController.text = '1';
      _step = 3;
    });
  }

  Future<void> _submitReturn() async {
    final int returnQty = int.tryParse(_qtyController.text.trim()) ?? 0;
    final int maxReturnable = (_selectedItem['quantity'] ?? 0) - (_selectedItem['returned_quantity'] ?? 0);

    if (returnQty <= 0) {
      setState(() => _submitError = 'Return quantity must be at least 1');
      return;
    }
    if (returnQty > maxReturnable) {
      setState(() => _submitError = 'Return quantity cannot exceed $maxReturnable');
      return;
    }

    setState(() {
      _isSubmitting = true;
      _submitError = null;
    });

    try {
      await ApiService.processSaleReturn(
        saleId: _selectedSale['id'],
        saleItemId: _selectedItem['id'],
        returnQuantity: returnQty,
        reason: _reasonController.text.trim().isEmpty ? 'Customer Return' : _reasonController.text.trim(),
      );

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Return processed successfully! Inventory restored.'),
          backgroundColor: AppColors.statusSafe,
        ),
      );
      Navigator.pop(context, true);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isSubmitting = false;
        _submitError = e.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      padding: EdgeInsets.only(
        left: AppSpacing.md,
        right: AppSpacing.md,
        top: AppSpacing.md,
        bottom: MediaQuery.of(context).viewInsets.bottom + AppSpacing.md,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header & Stepper
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  if (_step > 1)
                    IconButton(
                      icon: const Icon(Icons.arrow_back),
                      onPressed: () => setState(() => _step = 1),
                    ),
                  Text('Process Return (Step $_step/3)', style: AppTypography.heading3),
                ],
              ),
              IconButton(
                icon: const Icon(Icons.close),
                onPressed: () => Navigator.pop(context),
              ),
            ],
          ),
          const Divider(),

          // STEP 1: Search Original Sales / Medicine
          if (_step == 1) ...[
            const Text(
              'Search Original Sale Bill',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
            ),
            const SizedBox(height: 4),
            const Text(
              'Search medicine name or bill number directly from backend database:',
              style: TextStyle(color: AppColors.textMuted, fontSize: 12),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    decoration: const InputDecoration(
                      hintText: 'Enter medicine name or Bill #',
                      border: OutlineInputBorder(),
                      contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    ),
                    onChanged: (val) => _searchQuery = val,
                    onSubmitted: (_) => _performSearch(),
                  ),
                ),
                const SizedBox(width: 8),
                ElevatedButton(
                  onPressed: _isSearching ? null : _performSearch,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.brandDeep,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                  ),
                  child: _isSearching
                      ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Text('Search'),
                ),
              ],
            ),
            const SizedBox(height: 12),

            if (_searchError != null)
              Text('Error: $_searchError', style: const TextStyle(color: Colors.red)),

            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 280),
              child: _searchResults.isEmpty
                  ? Center(
                      child: Padding(
                        padding: const EdgeInsets.all(24.0),
                        child: Text(
                          _searchQuery.isEmpty ? 'Type search query above' : 'No sales found matching search',
                          style: const TextStyle(color: AppColors.textMuted),
                        ),
                      ),
                    )
                  : ListView.builder(
                      shrinkWrap: true,
                      itemCount: _searchResults.length,
                      itemBuilder: (context, index) {
                        final sale = _searchResults[index];
                        final items = sale['items'] as List<dynamic>? ?? [];

                        return Card(
                          margin: const EdgeInsets.only(bottom: 8),
                          child: ExpansionTile(
                            title: Text(
                              'Bill #${sale['id']} • ${sale['customer_name'] ?? 'Walk-in'}',
                              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                            ),
                            subtitle: Text(
                              'Date: ${sale['sale_date'] ?? ''} • Total: ₹${sale['total_amount']}',
                              style: const TextStyle(fontSize: 11, color: AppColors.textMuted),
                            ),
                            children: items.map<Widget>((item) {
                              final returnedQty = item['returned_quantity'] ?? 0;
                              final available = (item['quantity'] ?? 0) - returnedQty;
                              final isAvailable = available > 0;

                              return ListTile(
                                dense: true,
                                title: Text(
                                  item['product_name'] ?? 'Medicine',
                                  style: TextStyle(
                                    fontWeight: FontWeight.w600,
                                    color: isAvailable ? AppColors.textPrimary : AppColors.textMuted,
                                  ),
                                ),
                                subtitle: Text(
                                  'Batch: ${item['batch_number'] ?? 'N/A'} | Price: ₹${item['unit_price']} | Sold: ${item['quantity']} | Returned: $returnedQty',
                                  style: const TextStyle(fontSize: 11),
                                ),
                                trailing: ElevatedButton(
                                  onPressed: isAvailable ? () => _selectSaleAndItem(sale, item) : null,
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor: isAvailable ? AppColors.brandDeep : Colors.grey,
                                    foregroundColor: Colors.white,
                                  ),
                                  child: Text(isAvailable ? 'Return' : 'Fully Returned', style: const TextStyle(fontSize: 11)),
                                ),
                              );
                            }).toList(),
                          ),
                        );
                      },
                    ),
            ),
          ],

          // STEP 3: Confirm Return Details
          if (_step == 3 && _selectedItem != null) ...[
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppColors.brandDeep.withOpacity(0.05),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppColors.brandDeep.withOpacity(0.2)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _selectedItem['product_name'] ?? 'Medicine',
                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15),
                  ),
                  const SizedBox(height: 4),
                  Text('Bill #${_selectedSale['id']} • Customer: ${_selectedSale['customer_name'] ?? 'Walk-in'}'),
                  Text('Batch: ${_selectedItem['batch_number'] ?? 'N/A'} • Price: ₹${_selectedItem['unit_price']}'),
                  const SizedBox(height: 4),
                  Text(
                    'Available Returnable Qty: ${(_selectedItem['quantity'] ?? 0) - (_selectedItem['returned_quantity'] ?? 0)} unit(s)',
                    style: const TextStyle(fontWeight: FontWeight.bold, color: AppColors.brandDeep),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),

            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _qtyController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: 'Return Quantity',
                      border: OutlineInputBorder(),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextField(
                    controller: _reasonController,
                    decoration: const InputDecoration(
                      labelText: 'Return Reason',
                      border: OutlineInputBorder(),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),

            if (_submitError != null)
              Text('Error: $_submitError', style: const TextStyle(color: Colors.red)),

            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: _isSubmitting ? null : _submitReturn,
                icon: const Icon(Icons.check_circle_outline),
                label: Text(_isSubmitting ? 'Processing Return...' : 'Confirm Return & Restore Stock'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.brandDeep,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
