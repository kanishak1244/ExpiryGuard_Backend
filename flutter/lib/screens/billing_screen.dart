import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../theme/app_spacing.dart';
import '../widgets/status_badge.dart';
import '../widgets/tabular_text.dart';

/// Customer data model for retail counter billing
class CustomerParty {
  final int id;
  final String name;
  final String phone;
  final String gstin;
  final String address;

  const CustomerParty({
    required this.id,
    required this.name,
    required this.phone,
    this.gstin = '',
    this.address = '',
  });
}

/// Retail POS Item Entry Model with FEFO batch selection and live tax calculations
class PosBillItem {
  String id;
  String medicineName;
  String brand;
  String composition;
  String hsnCode;
  String selectedBatch;
  String expiryDate;
  int availableStock;
  int quantity;
  int freeQuantity;
  double rate;
  double discountPercent;
  double gstRate;
  List<ProductBatchOption> availableBatches;

  PosBillItem({
    required this.id,
    required this.medicineName,
    required this.brand,
    this.composition = '',
    this.hsnCode = '3004',
    required this.selectedBatch,
    required this.expiryDate,
    required this.availableStock,
    this.quantity = 1,
    this.freeQuantity = 0,
    required this.rate,
    this.discountPercent = 0.0,
    this.gstRate = 12.0,
    required this.availableBatches,
  });

  double get taxableAmount {
    final effectivePrice = rate * (1.0 - (discountPercent / 100.0));
    return effectivePrice * quantity;
  }

  double get gstAmount => taxableAmount * (gstRate / 100.0);
  double get cgstAmount => gstAmount / 2.0;
  double get sgstAmount => gstAmount / 2.0;
  double get totalWithTax => taxableAmount + gstAmount;
}

class BillingScreen extends StatefulWidget {
  const BillingScreen({super.key});

  @override
  State<BillingScreen> createState() => _BillingScreenState();
}

class _BillingScreenState extends State<BillingScreen> {
  // 1. Header State
  final List<CustomerParty> _customers = [
    const CustomerParty(id: 1, name: 'Walk-in Customer', phone: 'Cash Sale', gstin: ''),
    const CustomerParty(id: 2, name: 'Rajesh Sharma', phone: '+91 98765 43210', gstin: '07AAAAA0000A1Z5', address: 'B-12, Green Park, New Delhi'),
    const CustomerParty(id: 3, name: 'Pooja Verma', phone: '+91 98111 22334', gstin: '', address: 'Sector 14, Gurugram'),
    const CustomerParty(id: 4, name: 'Dr. Alok Clinic (B2B)', phone: '+91 99887 76655', gstin: '07AAECP4589K1ZR', address: 'South Ext Part 2'),
  ];
  late CustomerParty _selectedCustomer;

  String _invoiceNumber = 'INV-2026-0048';
  DateTime _invoiceDate = DateTime.now();
  String _paymentMode = 'Cash'; // Cash, UPI, Credit

  // 2. Mock Medicine Catalog with FEFO Batch Stock
  final List<Map<String, dynamic>> _medicineCatalog = [
    {
      'name': 'Augmentin 625 Duo Tablet',
      'brand': 'GlaxoSmithKline',
      'composition': 'Amoxicillin (500mg) + Clavulanic Acid (125mg)',
      'hsn': '3004',
      'mrp': 204.80,
      'gst': 12.0,
      'batches': [
        {'batch': 'AUG8921', 'expiry': '2027-08-31', 'stock': 40, 'mrp': 204.80},
        {'batch': 'AUG9012', 'expiry': '2028-02-28', 'stock': 60, 'mrp': 204.80},
      ]
    },
    {
      'name': 'Dolo 650mg Tablet',
      'brand': 'Micro Labs Ltd',
      'composition': 'Paracetamol IP (650mg)',
      'hsn': '3004',
      'mrp': 33.60,
      'gst': 12.0,
      'batches': [
        {'batch': 'DOL901', 'expiry': '2027-11-15', 'stock': 120, 'mrp': 33.60},
        {'batch': 'DOL944', 'expiry': '2028-05-30', 'stock': 85, 'mrp': 33.60},
      ]
    },
    {
      'name': 'Pan 40mg Tablet',
      'brand': 'Alkem Laboratories',
      'composition': 'Pantoprazole Gastro-resistant (40mg)',
      'hsn': '3004',
      'mrp': 155.00,
      'gst': 12.0,
      'batches': [
        {'batch': 'PN4401', 'expiry': '2028-01-30', 'stock': 100, 'mrp': 155.00},
      ]
    },
    {
      'name': 'Azee 500mg Tablet',
      'brand': 'Cipla Ltd',
      'composition': 'Azithromycin (500mg)',
      'hsn': '3004',
      'mrp': 119.50,
      'gst': 12.0,
      'batches': [
        {'batch': 'AZ5520', 'expiry': '2027-11-30', 'stock': 50, 'mrp': 119.50},
      ]
    },
    {
      'name': 'Telma 40mg Tablet',
      'brand': 'Glenmark Pharma',
      'composition': 'Telmisartan (40mg)',
      'hsn': '3004',
      'mrp': 128.00,
      'gst': 12.0,
      'batches': [
        {'batch': 'TL8810', 'expiry': '2027-12-15', 'stock': 90, 'mrp': 128.00},
      ]
    },
    {
      'name': 'Ecosprin AV 75/20 Capsule',
      'brand': 'USV Ltd',
      'composition': 'Aspirin (75mg) + Atorvastatin (20mg)',
      'hsn': '3004',
      'mrp': 66.80,
      'gst': 12.0,
      'batches': [
        {'batch': '28028429', 'expiry': '2026-09-15', 'stock': 18, 'mrp': 66.80},
      ]
    },
  ];

  // 3. Running Bill Items
  final List<PosBillItem> _billItems = [];

  // Active Row Inputs / Search
  final TextEditingController _searchController = TextEditingController();
  final FocusNode _searchFocusNode = FocusNode();
  List<Map<String, dynamic>> _filteredSuggestions = [];
  bool _isSearching = false;

  // Bill-Level Calculations State
  double _billDiscountPercent = 0.0;
  double _manualRoundOff = 0.0;
  bool _useManualRoundOff = false;

  @override
  void initState() {
    super.initState();
    _selectedCustomer = _customers.first;
    _generateNextInvoiceNumber();

    // Start with 2 initial pre-loaded items for quick preview
    _addItemFromCatalog(_medicineCatalog[0], initialQty: 2);
    _addItemFromCatalog(_medicineCatalog[1], initialQty: 3);
  }

  @override
  void dispose() {
    _searchController.dispose();
    _searchFocusNode.dispose();
    super.dispose();
  }

  void _generateNextInvoiceNumber() {
    final timestamp = DateTime.now().millisecondsSinceEpoch % 10000;
    setState(() {
      _invoiceNumber = 'INV-2026-${timestamp.toString().padLeft(4, '0')}';
    });
  }

  // ==========================================
  // MATHEMATICAL CALCULATIONS (POS Billing Engine)
  // ==========================================

  double get rawSubtotal => _billItems.fold(0.0, (sum, item) => sum + item.taxableAmount);

  double get billDiscountAmount => rawSubtotal * (_billDiscountPercent / 100.0);

  double get netTaxableSubtotal => (rawSubtotal - billDiscountAmount).clamp(0.0, double.infinity);

  double get totalGstAmount {
    if (rawSubtotal == 0.0) return 0.0;
    final discountRatio = netTaxableSubtotal / rawSubtotal;
    return _billItems.fold(0.0, (sum, item) => sum + (item.gstAmount * discountRatio));
  }

  double get totalCgstAmount => totalGstAmount / 2.0;
  double get totalSgstAmount => totalGstAmount / 2.0;

  double get unroundedGrandTotal => netTaxableSubtotal + totalGstAmount;

  double get calculatedRoundOff {
    if (_useManualRoundOff) return _manualRoundOff;
    final rounded = unroundedGrandTotal.roundToDouble();
    return rounded - unroundedGrandTotal;
  }

  double get grandTotal => (unroundedGrandTotal + calculatedRoundOff).clamp(0.0, double.infinity);

  int get totalQuantityCount => _billItems.fold(0, (sum, item) => sum + item.quantity);

  // ==========================================
  // ITEM & BATCH MANAGEMENT
  // ==========================================

  void _addItemFromCatalog(Map<String, dynamic> med, {int initialQty = 1}) {
    final batches = List<Map<String, dynamic>>.from(med['batches'] ?? []);
    // FEFO: Sort by expiry date ascending
    batches.sort((a, b) => (a['expiry'] as String).compareTo(b['expiry'] as String));

    final primaryBatch = batches.isNotEmpty
        ? batches.first
        : {'batch': 'BATCH-01', 'expiry': '2027-12-31', 'stock': 100, 'mrp': med['mrp']};

    setState(() {
      _billItems.add(
        PosBillItem(
          id: DateTime.now().microsecondsSinceEpoch.toString(),
          medicineName: med['name'],
          brand: med['brand'],
          composition: med['composition'] ?? '',
          hsnCode: med['hsn'] ?? '3004',
          selectedBatch: primaryBatch['batch'],
          expiryDate: primaryBatch['expiry'],
          availableStock: primaryBatch['stock'] as int,
          quantity: initialQty,
          freeQuantity: 0,
          rate: (primaryBatch['mrp'] as num).toDouble(),
          discountPercent: 0.0,
          gstRate: (med['gst'] as num?)?.toDouble() ?? 12.0,
          availableBatches: batches,
        ),
      );
      _searchController.clear();
      _filteredSuggestions.clear();
      _isSearching = false;
    });
  }

  void _onSearchChanged(String query) {
    if (query.trim().isEmpty) {
      setState(() {
        _filteredSuggestions = [];
        _isSearching = false;
      });
      return;
    }

    final q = query.toLowerCase();
    final matches = _medicineCatalog.where((m) {
      final name = (m['name'] as String).toLowerCase();
      final brand = (m['brand'] as String).toLowerCase();
      final comp = ((m['composition'] as String?) ?? '').toLowerCase();
      return name.contains(q) || brand.contains(q) || comp.contains(q);
    }).toList();

    setState(() {
      _filteredSuggestions = matches;
      _isSearching = true;
    });
  }

  // ==========================================
  // CUSTOMER / PARTY SELECTION & INLINE MODAL
  // ==========================================

  void _showCustomerPickerSheet() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(16))),
      builder: (ctx) {
        String searchQuery = '';
        return StatefulBuilder(
          builder: (context, setSheetState) {
            final filtered = _customers.where((c) {
              return c.name.toLowerCase().contains(searchQuery.toLowerCase()) ||
                     c.phone.toLowerCase().contains(searchQuery.toLowerCase());
            }).toList();

            return Container(
              height: MediaQuery.of(context).size.height * 0.75,
              padding: const EdgeInsets.all(AppSpacing.lg),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text('Select Customer / Patient Party', style: AppTypography.sectionTitle),
                      IconButton(icon: const Icon(Icons.close), onPressed: () => Navigator.pop(ctx)),
                    ],
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    decoration: InputDecoration(
                      hintText: 'Search customer name or phone...',
                      prefixIcon: const Icon(Icons.search, size: 20),
                      fillColor: AppColors.surfaceBg,
                    ),
                    onChanged: (val) {
                      setSheetState(() {
                        searchQuery = val;
                      });
                    },
                  ),
                  const SizedBox(height: 12),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: OutlinedButton.icon(
                      onPressed: () {
                        Navigator.pop(ctx);
                        _showAddNewCustomerDialog();
                      },
                      icon: const Icon(Icons.person_add_alt_1, size: 16),
                      label: const Text('+ Add New Party / Customer'),
                    ),
                  ),
                  const Divider(height: 20),
                  Expanded(
                    child: ListView.separated(
                      itemCount: filtered.length,
                      separatorBuilder: (_, __) => const Divider(height: 1, color: AppColors.border),
                      itemBuilder: (context, idx) {
                        final cust = filtered[idx];
                        final isSelected = cust.id == _selectedCustomer.id;

                        return ListTile(
                          contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          leading: CircleAvatar(
                            backgroundColor: isSelected ? AppColors.brandDeep : const Color(0xFFE2E8F0),
                            child: Icon(
                              cust.id == 1 ? Icons.storefront : Icons.person,
                              color: isSelected ? Colors.white : AppColors.textMuted,
                              size: 20,
                            ),
                          ),
                          title: Text(cust.name, style: TextStyle(fontWeight: isSelected ? FontWeight.bold : FontWeight.w600)),
                          subtitle: Text('${cust.phone}${cust.gstin.isNotEmpty ? ' • GSTIN: ${cust.gstin}' : ''}', style: AppTypography.bodyMuted),
                          trailing: isSelected ? const Icon(Icons.check_circle, color: AppColors.brandDeep) : null,
                          onTap: () {
                            setState(() {
                              _selectedCustomer = cust;
                            });
                            Navigator.pop(ctx);
                          },
                        );
                      },
                    ),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  void _showAddNewCustomerDialog() {
    final nameCtrl = TextEditingController();
    final phoneCtrl = TextEditingController();
    final gstinCtrl = TextEditingController();

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Add New Customer Party'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: nameCtrl,
              decoration: const InputDecoration(labelText: 'Customer / Patient Name *'),
              autofocus: true,
            ),
            const SizedBox(height: 10),
            TextField(
              controller: phoneCtrl,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(labelText: 'Mobile Number *'),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: gstinCtrl,
              textCapitalization: TextCapitalization.characters,
              decoration: const InputDecoration(labelText: 'GSTIN (Optional)'),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          ElevatedButton(
            onPressed: () {
              if (nameCtrl.text.trim().isEmpty || phoneCtrl.text.trim().isEmpty) return;
              final newCust = CustomerParty(
                id: DateTime.now().millisecondsSinceEpoch,
                name: nameCtrl.text.trim(),
                phone: phoneCtrl.text.trim(),
                gstin: gstinCtrl.text.trim(),
              );
              setState(() {
                _customers.add(newCust);
                _selectedCustomer = newCust;
              });
              Navigator.pop(ctx);
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text('Customer "${newCust.name}" added and selected.')),
              );
            },
            child: const Text('Save Customer'),
          ),
        ],
      ),
    );
  }

  // ==========================================
  // ACTIONS: SAVE & PRINT / SAVE & NEW / DRAFT
  // ==========================================

  void _saveAndPrintBill() {
    if (_billItems.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Cannot print empty bill. Please add medicines.')),
      );
      return;
    }

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Row(
          children: [
            Icon(Icons.check_circle_outline, color: AppColors.statusSafe),
            SizedBox(width: 8),
            Text('Bill Confirmed & Saved'),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Invoice No: $_invoiceNumber', style: const TextStyle(fontWeight: FontWeight.bold)),
            Text('Customer: ${_selectedCustomer.name}'),
            Text('Payment Mode: $_paymentMode'),
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFFF1F5F9),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('Grand Total Paid:'),
                  TabularCurrency(amount: grandTotal, style: AppTypography.numericPrice.copyWith(fontSize: 16)),
                ],
              ),
            ),
            const SizedBox(height: 12),
            const Text(
              'Stock automatically deducted in FEFO priority order. GST invoice PDF generated ready for thermal/A4 printing.',
              style: TextStyle(fontSize: 12, color: AppColors.textMuted),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () {
              Navigator.pop(ctx);
              _resetForNewBill();
            },
            child: const Text('New Bill'),
          ),
          ElevatedButton.icon(
            icon: const Icon(Icons.print, size: 16),
            label: const Text('Print / Share PDF'),
            onPressed: () {
              Navigator.pop(ctx);
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text('Printing $_invoiceNumber (PDF dispatched to printer)...'),
                  backgroundColor: AppColors.brandDeep,
                ),
              );
              _resetForNewBill();
            },
          ),
        ],
      ),
    );
  }

  void _saveAndNewBill() {
    if (_billItems.isEmpty) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Bill $_invoiceNumber saved successfully! Ready for next customer.'),
        backgroundColor: const Color(0xFF059669),
      ),
    );
    _resetForNewBill();
  }

  void _saveDraftBill() {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Bill $_invoiceNumber saved as Draft.'),
        backgroundColor: AppColors.brandDeep,
      ),
    );
  }

  void _resetForNewBill() {
    setState(() {
      _billItems.clear();
      _selectedCustomer = _customers.first;
      _billDiscountPercent = 0.0;
      _useManualRoundOff = false;
      _generateNextInvoiceNumber();
    });
  }

  // ==========================================
  // MAIN UI BUILD
  // ==========================================

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Counter POS Billing'),
        actions: [
          IconButton(
            icon: const Icon(Icons.save_as_outlined),
            tooltip: 'Save Draft',
            onPressed: _billItems.isEmpty ? null : _saveDraftBill,
          ),
          IconButton(
            icon: const Icon(Icons.restart_alt),
            tooltip: 'Clear / Reset Bill',
            onPressed: _billItems.isEmpty ? null : _resetForNewBill,
          ),
        ],
      ),
      body: Column(
        children: [
          // Scrollable upper content
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // 1. Header Section: Customer, Invoice No, Date, Payment Mode
                  _buildHeaderSection(),
                  const SizedBox(height: AppSpacing.md),

                  // 2. Search & Fast Item Entry Bar
                  _buildSearchAndAddBar(),
                  const SizedBox(height: AppSpacing.md),

                  // 3. Running Items Table / Cards
                  _buildItemsSectionHeader(),
                  const SizedBox(height: AppSpacing.xs),
                  if (_billItems.isEmpty)
                    _buildEmptyBillPlaceholder()
                  else
                    ..._billItems.asMap().entries.map((entry) => _buildPosItemCard(entry.value, entry.key)),

                  const SizedBox(height: AppSpacing.md),

                  // 4. Totals & Tax Breakup Section
                  if (_billItems.isNotEmpty) _buildFooterTotalsSection(),
                  const SizedBox(height: 20),
                ],
              ),
            ),
          ),

          // 5. Bottom Action Bar (Fixed, Always Visible)
          _buildBottomActionBar(),
        ],
      ),
    );
  }

  // ==========================================
  // SECTION 1: HEADER SECTION
  // ==========================================

  Widget _buildHeaderSection() {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surfaceCard,
        borderRadius: AppSpacing.roundedMd,
        border: Border.all(color: AppColors.border),
        boxShadow: AppSpacing.shadowSubtle,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Customer Selector Row
          InkWell(
            onTap: _showCustomerPickerSheet,
            borderRadius: BorderRadius.circular(8),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              decoration: BoxDecoration(
                color: AppColors.surfaceBg,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppColors.border),
              ),
              child: Row(
                children: [
                  const Icon(Icons.person_pin, color: AppColors.brandDeep, size: 22),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          _selectedCustomer.name,
                          style: const TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: AppColors.textPrimary),
                        ),
                        Text(
                          '${_selectedCustomer.phone}${_selectedCustomer.gstin.isNotEmpty ? '  •  ${_selectedCustomer.gstin}' : ''}',
                          style: AppTypography.bodyMuted.copyWith(fontSize: 11.5),
                        ),
                      ],
                    ),
                  ),
                  const Icon(Icons.arrow_drop_down, color: AppColors.textMuted),
                ],
              ),
            ),
          ),

          const SizedBox(height: 12),

          // Invoice Number, Date, and Payment Mode
          Row(
            children: [
              // Invoice No
              Expanded(
                flex: 4,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Invoice No', style: TextStyle(fontSize: 11, color: AppColors.textMuted, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 4),
                    TextFormField(
                      initialValue: _invoiceNumber,
                      style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
                      decoration: InputDecoration(
                        isDense: true,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                        fillColor: AppColors.surfaceBg,
                      ),
                      onChanged: (val) => _invoiceNumber = val,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),

              // Invoice Date
              Expanded(
                flex: 4,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Date', style: TextStyle(fontSize: 11, color: AppColors.textMuted, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 4),
                    InkWell(
                      onTap: () async {
                        final picked = await showDatePicker(
                          context: context,
                          initialDate: _invoiceDate,
                          firstDate: DateTime(2025),
                          lastDate: DateTime(2030),
                        );
                        if (picked != null) setState(() => _invoiceDate = picked);
                      },
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
                        decoration: BoxDecoration(
                          color: AppColors.surfaceBg,
                          borderRadius: BorderRadius.circular(6),
                          border: Border.all(color: AppColors.border),
                        ),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              '${_invoiceDate.day.toString().padLeft(2, '0')}-${_invoiceDate.month.toString().padLeft(2, '0')}-${_invoiceDate.year}',
                              style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w500),
                            ),
                            const Icon(Icons.calendar_today, size: 14, color: AppColors.textMuted),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),

          const SizedBox(height: 12),

          // Payment Mode Segmented Control
          Row(
            children: [
              const Text('Pay Mode: ', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.textMuted)),
              const SizedBox(width: 8),
              Expanded(
                child: SegmentedButton<String>(
                  segments: const [
                    ButtonSegment(value: 'Cash', label: Text('💵 Cash', style: TextStyle(fontSize: 12))),
                    ButtonSegment(value: 'UPI', label: Text('📱 UPI', style: TextStyle(fontSize: 12))),
                    ButtonSegment(value: 'Credit', label: Text('📋 Credit', style: TextStyle(fontSize: 12))),
                  ],
                  selected: {_paymentMode},
                  onSelectionChanged: (val) {
                    setState(() {
                      _paymentMode = val.first;
                    });
                  },
                  style: ButtonStyle(
                    visualDensity: VisualDensity.compact,
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  // ==========================================
  // SECTION 2: SEARCH-AS-YOU-TYPE AUTOCOMPLETE
  // ==========================================

  Widget _buildSearchAndAddBar() {
    return Column(
      children: [
        TextField(
          controller: _searchController,
          focusNode: _searchFocusNode,
          onChanged: _onSearchChanged,
          decoration: InputDecoration(
            hintText: 'Search medicine name, brand, or generic salt...',
            prefixIcon: const Icon(Icons.search, color: AppColors.brandDeep),
            suffixIcon: _searchController.text.isNotEmpty
                ? IconButton(
                    icon: const Icon(Icons.clear, size: 18),
                    onPressed: () {
                      _searchController.clear();
                      _onSearchChanged('');
                    },
                  )
                : null,
            fillColor: Colors.white,
          ),
        ),

        // Autocomplete Suggestion Dropdown
        if (_isSearching && _filteredSuggestions.isNotEmpty)
          Container(
            margin: const EdgeInsets.only(top: 4),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppColors.border),
              boxShadow: const [BoxShadow(color: Colors.black12, blurRadius: 8, offset: Offset(0, 4))],
            ),
            constraints: const BoxConstraints(maxHeight: 220),
            child: ListView.separated(
              shrinkWrap: true,
              itemCount: _filteredSuggestions.length,
              separatorBuilder: (_, __) => const Divider(height: 1, color: AppColors.border),
              itemBuilder: (context, idx) {
                final med = _filteredSuggestions[idx];
                final batches = List<Map<String, dynamic>>.from(med['batches'] ?? []);
                final topBatch = batches.isNotEmpty ? batches.first : null;

                return ListTile(
                  dense: true,
                  title: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Expanded(
                        child: Text(
                          med['name'],
                          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13.5),
                        ),
                      ),
                      Text('MRP ₹${med['mrp']}', style: const TextStyle(fontWeight: FontWeight.bold, color: AppColors.brandDeep)),
                    ],
                  ),
                  subtitle: Row(
                    children: [
                      Text(med['brand'], style: const TextStyle(fontSize: 11, color: AppColors.textMuted)),
                      if (topBatch != null) ...[
                        const Text('  •  ', style: TextStyle(color: AppColors.textMuted)),
                        Text('FEFO Batch: ${topBatch['batch']} (Stock: ${topBatch['stock']})', style: const TextStyle(fontSize: 11, color: AppColors.statusSafeText)),
                      ],
                    ],
                  ),
                  trailing: const Icon(Icons.add_circle, color: AppColors.brandDeep, size: 22),
                  onTap: () => _addItemFromCatalog(med),
                );
              },
            ),
          ),
      ],
    );
  }

  // ==========================================
  // SECTION 3: RUNNING BILL ITEMS (POS ROWS)
  // ==========================================

  Widget _buildItemsSectionHeader() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Row(
          children: [
            const Text('Billed Items', style: AppTypography.sectionTitle),
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(
                color: const Color(0xFFF1F5F9),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                '${_billItems.length} lines  •  $totalQuantityCount units',
                style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.w600, color: AppColors.textMuted),
              ),
            ),
          ],
        ),
        TextButton.icon(
          onPressed: () {
            _searchFocusNode.requestFocus();
          },
          icon: const Icon(Icons.add, size: 16),
          label: const Text('Add Row'),
        ),
      ],
    );
  }

  Widget _buildEmptyBillPlaceholder() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 36, horizontal: 20),
      decoration: BoxDecoration(
        color: AppColors.surfaceCard,
        borderRadius: AppSpacing.roundedMd,
        border: Border.all(color: AppColors.border),
      ),
      child: const Column(
        children: [
          Icon(Icons.receipt_long_outlined, size: 40, color: AppColors.textMuted),
          SizedBox(height: 8),
          Text('No medicines added to bill yet', style: TextStyle(fontWeight: FontWeight.bold)),
          SizedBox(height: 4),
          Text('Search medicine name above to add items via FEFO.', style: TextStyle(fontSize: 12, color: AppColors.textMuted)),
        ],
      ),
    );
  }

  Widget _buildPosItemCard(PosBillItem item, int index) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surfaceCard,
        borderRadius: AppSpacing.roundedMd,
        border: Border.all(color: AppColors.border),
        boxShadow: AppSpacing.shadowSubtle,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Row Header: Medicine Title + Delete
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('${index + 1}. ', style: const TextStyle(fontWeight: FontWeight.bold, color: AppColors.textMuted)),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item.medicineName, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                    Text('${item.brand}  •  HSN: ${item.hsnCode}', style: AppTypography.bodyMuted.copyWith(fontSize: 11)),
                  ],
                ),
              ),
              IconButton(
                icon: const Icon(Icons.delete_outline, color: AppColors.statusDanger, size: 20),
                visualDensity: VisualDensity.compact,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(),
                onPressed: () {
                  setState(() {
                    _billItems.removeAt(index);
                  });
                },
              ),
            ],
          ),

          const SizedBox(height: 8),

          // Batch Override Dropdown & Expiry
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: AppColors.surfaceBg,
              borderRadius: BorderRadius.circular(6),
              border: Border.all(color: AppColors.border),
            ),
            child: Row(
              children: [
                const Text('Batch: ', style: TextStyle(fontSize: 11.5, fontWeight: FontWeight.w600, color: AppColors.textMuted)),
                const SizedBox(width: 4),
                if (item.availableBatches.length > 1)
                  DropdownButton<String>(
                    value: item.selectedBatch,
                    isDense: true,
                    underline: const SizedBox(),
                    style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: AppColors.textPrimary),
                    items: item.availableBatches.map((b) {
                      return DropdownMenuItem<String>(
                        value: b['batch'] as String,
                        child: Text('${b['batch']} (Exp: ${b['expiry']})'),
                      );
                    }).toList(),
                    onChanged: (newBatch) {
                      if (newBatch == null) return;
                      final bData = item.availableBatches.firstWhere((b) => b['batch'] == newBatch);
                      setState(() {
                        item.selectedBatch = newBatch;
                        item.expiryDate = bData['expiry'];
                        item.availableStock = bData['stock'] as int;
                        item.rate = (bData['mrp'] as num).toDouble();
                      });
                    },
                  )
                else
                  Text('${item.selectedBatch} (Exp: ${item.expiryDate})', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                const Spacer(),
                Text('Avail: ${item.availableStock}', style: const TextStyle(fontSize: 11.5, color: AppColors.statusSafeText, fontWeight: FontWeight.w600)),
              ],
            ),
          ),

          const SizedBox(height: 10),

          // POS Core Input Columns: Qty | Free | Rate | Disc% | GST% | Amount
          Row(
            children: [
              // Qty
              Expanded(
                flex: 2,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Qty', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.textMuted)),
                    const SizedBox(height: 2),
                    TextFormField(
                      initialValue: item.quantity.toString(),
                      keyboardType: TextInputType.number,
                      textInputAction: TextInputAction.next,
                      decoration: InputDecoration(
                        isDense: true,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                        fillColor: AppColors.surfaceBg,
                      ),
                      onChanged: (val) {
                        setState(() {
                          item.quantity = int.tryParse(val) ?? 1;
                        });
                      },
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 6),

              // Free Qty
              Expanded(
                flex: 2,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Free', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.textMuted)),
                    const SizedBox(height: 2),
                    TextFormField(
                      initialValue: item.freeQuantity.toString(),
                      keyboardType: TextInputType.number,
                      decoration: InputDecoration(
                        isDense: true,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                        fillColor: AppColors.surfaceBg,
                      ),
                      onChanged: (val) {
                        setState(() {
                          item.freeQuantity = int.tryParse(val) ?? 0;
                        });
                      },
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 6),

              // Rate (₹)
              Expanded(
                flex: 3,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Rate (₹)', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.textMuted)),
                    const SizedBox(height: 2),
                    TextFormField(
                      initialValue: item.rate.toStringAsFixed(2),
                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      decoration: InputDecoration(
                        isDense: true,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                        fillColor: AppColors.surfaceBg,
                      ),
                      onChanged: (val) {
                        setState(() {
                          item.rate = double.tryParse(val) ?? 0.0;
                        });
                      },
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 6),

              // Disc %
              Expanded(
                flex: 2,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Disc%', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.textMuted)),
                    const SizedBox(height: 2),
                    TextFormField(
                      initialValue: item.discountPercent.toStringAsFixed(0),
                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      decoration: InputDecoration(
                        isDense: true,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                        fillColor: AppColors.surfaceBg,
                      ),
                      onChanged: (val) {
                        setState(() {
                          item.discountPercent = double.tryParse(val) ?? 0.0;
                        });
                      },
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 6),

              // GST %
              Expanded(
                flex: 2,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('GST%', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.textMuted)),
                    const SizedBox(height: 2),
                    TextFormField(
                      initialValue: item.gstRate.toStringAsFixed(0),
                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      decoration: InputDecoration(
                        isDense: true,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                        fillColor: AppColors.surfaceBg,
                      ),
                      onChanged: (val) {
                        setState(() {
                          item.gstRate = double.tryParse(val) ?? 12.0;
                        });
                      },
                    ),
                  ],
                ),
              ),
            ],
          ),

          const SizedBox(height: 8),

          // Row Amount & Tax calculation footer
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Taxable: ₹${item.taxableAmount.toStringAsFixed(2)} + GST: ₹${item.gstAmount.toStringAsFixed(2)} (CGST ₹${item.cgstAmount.toStringAsFixed(2)} / SGST ₹${item.sgstAmount.toStringAsFixed(2)})',
                style: const TextStyle(fontSize: 10.5, color: AppColors.textMuted),
              ),
              Row(
                children: [
                  const Text('Row Total: ', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.textMuted)),
                  TabularCurrency(amount: item.totalWithTax, style: AppTypography.numericPrice.copyWith(fontSize: 14)),
                ],
              ),
            ],
          ),
        ],
      ),
    );
  }

  // ==========================================
  // SECTION 4: FOOTER / TOTALS & TAX BREAKUP
  // ==========================================

  Widget _buildFooterTotalsSection() {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surfaceCard,
        borderRadius: AppSpacing.roundedMd,
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        children: [
          // Subtotal
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('Subtotal (Item Total):', style: AppTypography.bodyMuted),
              TabularCurrency(amount: rawSubtotal, style: AppTypography.numericPrice),
            ],
          ),
          const SizedBox(height: 6),

          // Bill-Level Overall Discount
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  const Text('Bill Discount %: ', style: AppTypography.bodyMuted),
                  SizedBox(
                    width: 50,
                    child: TextFormField(
                      initialValue: _billDiscountPercent.toStringAsFixed(0),
                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      style: const TextStyle(fontSize: 12),
                      decoration: const InputDecoration(
                        isDense: true,
                        contentPadding: EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                      ),
                      onChanged: (val) {
                        setState(() {
                          _billDiscountPercent = double.tryParse(val) ?? 0.0;
                        });
                      },
                    ),
                  ),
                ],
              ),
              Text('- ₹${billDiscountAmount.toStringAsFixed(2)}', style: const TextStyle(color: AppColors.statusSafeText, fontWeight: FontWeight.w600)),
            ],
          ),

          const Divider(height: 16, color: AppColors.border),

          // Tax Breakup (CGST & SGST separately)
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('CGST Tax Breakup:', style: AppTypography.bodyMuted),
              TabularCurrency(amount: totalCgstAmount, style: AppTypography.numericPrice),
            ],
          ),
          const SizedBox(height: 4),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('SGST Tax Breakup:', style: AppTypography.bodyMuted),
              TabularCurrency(amount: totalSgstAmount, style: AppTypography.numericPrice),
            ],
          ),

          const SizedBox(height: 6),

          // Round Off
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('Round Off:', style: AppTypography.bodyMuted),
              Text(
                '${calculatedRoundOff >= 0 ? '+' : ''}₹${calculatedRoundOff.toStringAsFixed(2)}',
                style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500, color: AppColors.textMuted),
              ),
            ],
          ),

          const Divider(height: 16, color: AppColors.border),

          // Grand Total
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('Grand Total:', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
              TabularCurrency(
                amount: grandTotal,
                style: AppTypography.numericGrandTotal.copyWith(fontSize: 22, color: AppColors.brandDeep),
              ),
            ],
          ),
        ],
      ),
    );
  }

  // ==========================================
  // SECTION 5: BOTTOM ACTION BUTTONS
  // ==========================================

  Widget _buildBottomActionBar() {
    final hasItems = _billItems.isNotEmpty;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: Colors.white,
        border: const Border(top: BorderSide(color: AppColors.border)),
        boxShadow: const [BoxShadow(color: Colors.black12, blurRadius: 6, offset: Offset(0, -2))],
      ),
      child: SafeArea(
        child: Row(
          children: [
            // Save & New Button
            Expanded(
              flex: 4,
              child: OutlinedButton(
                onPressed: hasItems ? _saveAndNewBill : null,
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 12),
                ),
                child: const Text('Save & New', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
              ),
            ),
            const SizedBox(width: 10),

            // Save & Print Button (Primary)
            Expanded(
              flex: 6,
              child: ElevatedButton.icon(
                onPressed: hasItems ? _saveAndPrintBill : null,
                icon: const Icon(Icons.print, size: 18),
                label: const Text('Save & Print', style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold)),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.brandDeep,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 12),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
