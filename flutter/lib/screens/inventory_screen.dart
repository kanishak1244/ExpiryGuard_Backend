import 'package:flutter/material.dart';
import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../theme/app_spacing.dart';
import '../widgets/status_badge.dart';
import '../widgets/tabular_text.dart';

class InventoryScreen extends StatefulWidget {
  const InventoryScreen({super.key});

  @override
  State<InventoryScreen> createState() => _InventoryScreenState();
}

class _InventoryScreenState extends State<InventoryScreen> {
  String _activeFilter = 'all';
  bool _isSelectMode = false;
  final Set<int> _selectedIds = {};

  final List<Map<String, dynamic>> _inventory = [
    {
      'id': 1,
      'name': 'Eltroxin 75mcg Tablet',
      'category': 'Thyroid Care',
      'batch': '3W41',
      'quantity': 24,
      'unit': 'strip',
      'tablets_per_strip': 10,
      'loose_stock': 6,
      'mrp': 184.50,
      'expiry': '2028-03-01',
      'days_left': 560,
    },
    {
      'id': 2,
      'name': 'Udapa M 500mg XR Tab',
      'category': 'Diabetes Care',
      'batch': 'BRG03208B',
      'quantity': 4,
      'unit': 'strip',
      'tablets_per_strip': 10,
      'loose_stock': 2,
      'mrp': 145.75,
      'expiry': '2028-02-01',
      'days_left': 530,
    },
    {
      'id': 3,
      'name': 'Ecosprin AV 75/20 Cap',
      'category': 'Cardiology',
      'batch': '28028429',
      'quantity': 18,
      'unit': 'strip',
      'tablets_per_strip': 10,
      'loose_stock': 0,
      'mrp': 66.80,
      'expiry': '2026-09-15',
      'days_left': 27,
    },
  ];

  final List<Map<String, dynamic>> _recentlyDeleted = [];

  List<Map<String, dynamic>> get _filteredInventory {
    return _inventory.where((item) {
      if (_activeFilter == 'in_stock') return (item['quantity'] as int) > 0;
      if (_activeFilter == 'low_stock') return (item['quantity'] as int) > 0 && (item['quantity'] as int) <= 10;
      if (_activeFilter == 'expiring') return (item['days_left'] as int) > 0 && (item['days_left'] as int) <= 60;
      return true;
    }).toList();
  }

  void _toggleSelection(int id) {
    setState(() {
      if (_selectedIds.contains(id)) {
        _selectedIds.remove(id);
        if (_selectedIds.isEmpty) _isSelectMode = false;
      } else {
        _selectedIds.add(id);
        _isSelectMode = true;
      }
    });
  }

  void _toggleSelectAll() {
    setState(() {
      final visibleIds = _filteredInventory.map((e) => e['id'] as int).toSet();
      if (_selectedIds.containsAll(visibleIds)) {
        _selectedIds.removeAll(visibleIds);
        if (_selectedIds.isEmpty) _isSelectMode = false;
      } else {
        _selectedIds.addAll(visibleIds);
        _isSelectMode = true;
      }
    });
  }

  void _deleteSelected() {
    final count = _selectedIds.length;
    if (count == 0) return;

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Move to Recently Deleted'),
        content: Text('Are you sure you want to delete $count selected medicine batches?\n\nYou can recover them within 60 days from Recently Deleted.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.dangerRed),
            onPressed: () {
              Navigator.pop(ctx);
              setState(() {
                final removed = _inventory.where((e) => _selectedIds.contains(e['id'])).map((e) {
                  return {
                    ...e,
                    'deleted_at': DateTime.now(),
                    'days_until_permanent_delete': 60,
                  };
                }).toList();
                _recentlyDeleted.addAll(removed);
                _inventory.removeWhere((e) => _selectedIds.contains(e['id']));
                _selectedIds.clear();
                _isSelectMode = false;
              });

              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text('$count items moved to Recently Deleted, recoverable for 60 days.'),
                  backgroundColor: AppColors.brandDeep,
                  action: SnackBarAction(
                    label: 'VIEW',
                    textColor: Colors.white,
                    onPressed: _showRecentlyDeletedSheet,
                  ),
                ),
              );
            },
            child: const Text('Move to Deleted', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
  }

  void _deleteAllStock() {
    final totalCount = _inventory.length;
    if (totalCount == 0) return;

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Row(
          children: [
            Icon(Icons.warning_amber_rounded, color: AppColors.dangerRed),
            SizedBox(width: 8),
            Text('Delete All Stock'),
          ],
        ),
        content: Text(
          'This will remove all $totalCount items from inventory. You can recover them within 60 days.',
          style: const TextStyle(height: 1.4),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.dangerRed),
            onPressed: () {
              Navigator.pop(ctx);
              setState(() {
                final removed = _inventory.map((e) {
                  return {
                    ...e,
                    'deleted_at': DateTime.now(),
                    'days_until_permanent_delete': 60,
                  };
                }).toList();
                _recentlyDeleted.addAll(removed);
                _inventory.clear();
                _selectedIds.clear();
                _isSelectMode = false;
              });

              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text('All $totalCount items moved to Recently Deleted, recoverable for 60 days.'),
                  backgroundColor: AppColors.brandDeep,
                  action: SnackBarAction(
                    label: 'VIEW',
                    textColor: Colors.white,
                    onPressed: _showRecentlyDeletedSheet,
                  ),
                ),
              );
            },
            child: const Text('Yes, Delete All', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
  }

  void _showRecentlyDeletedSheet() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => StatefulBuilder(
        builder: (context, setModalState) {
          final deletedSelectSet = <int>{};

          return Container(
            height: MediaQuery.of(context).size.height * 0.85,
            decoration: const BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
            ),
            child: Column(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                  decoration: const BoxDecoration(
                    border: Border(bottom: BorderSide(color: AppColors.border)),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            '♻️ Recently Deleted (60-Day Recovery)',
                            style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            '${_recentlyDeleted.length} items in trash',
                            style: const TextStyle(fontSize: 12, color: AppColors.textMuted),
                          ),
                        ],
                      ),
                      IconButton(
                        icon: const Icon(Icons.close),
                        onPressed: () => Navigator.pop(ctx),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: _recentlyDeleted.isEmpty
                      ? const Center(
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.delete_outline, size: 48, color: AppColors.textMuted),
                              SizedBox(height: 8),
                              Text('No soft-deleted stock records', style: TextStyle(color: AppColors.textMuted)),
                            ],
                          ),
                        )
                      : ListView.separated(
                          padding: const EdgeInsets.all(16),
                          itemCount: _recentlyDeleted.length,
                          separatorBuilder: (_, __) => const SizedBox(height: 10),
                          itemBuilder: (context, idx) {
                            final delItem = _recentlyDeleted[idx];
                            final daysLeft = delItem['days_until_permanent_delete'] ?? 60;

                            return Container(
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: AppColors.surfaceCard,
                                borderRadius: AppSpacing.roundedMd,
                                border: Border.all(color: AppColors.border),
                              ),
                              child: Row(
                                children: [
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          delItem['name'] ?? '',
                                          style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
                                        ),
                                        const SizedBox(height: 4),
                                        Text(
                                          'Batch: ${delItem['batch']}  •  Qty: ${delItem['quantity']}',
                                          style: const TextStyle(fontSize: 12, color: AppColors.textMuted),
                                        ),
                                        const SizedBox(height: 6),
                                        Container(
                                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                          decoration: BoxDecoration(
                                            color: const Color(0xFFECFDF5),
                                            borderRadius: BorderRadius.circular(4),
                                            border: Border.all(color: const Color(0xFFA7F3D0)),
                                          ),
                                          child: Text(
                                            '$daysLeft days remaining',
                                            style: const TextStyle(fontSize: 11, color: Color(0xFF065F46), fontWeight: FontWeight.w600),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  ElevatedButton.icon(
                                    style: ElevatedButton.styleFrom(
                                      backgroundColor: const Color(0xFF059669),
                                      foregroundColor: Colors.white,
                                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                    ),
                                    icon: const Icon(Icons.restore, size: 16),
                                    label: const Text('Restore', style: TextStyle(fontSize: 12)),
                                    onPressed: () {
                                      setState(() {
                                        _inventory.add(delItem);
                                        _recentlyDeleted.removeAt(idx);
                                      });
                                      setModalState(() {});
                                      Navigator.pop(ctx);
                                      ScaffoldMessenger.of(context).showSnackBar(
                                        SnackBar(
                                          content: Text('${delItem['name']} restored to live inventory.'),
                                          backgroundColor: const Color(0xFF059669),
                                        ),
                                      );
                                    },
                                  ),
                                ],
                              ),
                            );
                          },
                        ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final filtered = _filteredInventory;
    final allSelected = filtered.isNotEmpty && _selectedIds.containsAll(filtered.map((e) => e['id'] as int));

    return Scaffold(
      appBar: AppBar(
        title: _isSelectMode
            ? Text('${_selectedIds.length} Selected')
            : const Text('Live Inventory & Stock'),
        leading: _isSelectMode
            ? IconButton(
                icon: const Icon(Icons.close),
                onPressed: () {
                  setState(() {
                    _isSelectMode = false;
                    _selectedIds.clear();
                  });
                },
              )
            : null,
        actions: [
          if (_isSelectMode) ...[
            IconButton(
              icon: Icon(allSelected ? Icons.deselect : Icons.select_all),
              tooltip: allSelected ? 'Deselect All' : 'Select All',
              onPressed: _toggleSelectAll,
            ),
            IconButton(
              icon: const Icon(Icons.delete_outline, color: AppColors.dangerRed),
              tooltip: 'Delete Selected',
              onPressed: _deleteSelected,
            ),
          ] else ...[
            IconButton(
              icon: const Icon(Icons.checklist_rounded),
              tooltip: 'Select Mode',
              onPressed: () {
                setState(() {
                  _isSelectMode = true;
                });
              },
            ),
            PopupMenuButton<String>(
              onSelected: (val) {
                if (val == 'recently_deleted') {
                  _showRecentlyDeletedSheet();
                } else if (val == 'delete_all') {
                  _deleteAllStock();
                }
              },
              itemBuilder: (context) => [
                const PopupMenuItem(
                  value: 'recently_deleted',
                  child: Row(
                    children: [
                      Icon(Icons.history, size: 18),
                      SizedBox(width: 8),
                      Text('Recently Deleted'),
                    ],
                  ),
                ),
                const PopupMenuItem(
                  value: 'delete_all',
                  child: Row(
                    children: [
                      Icon(Icons.delete_sweep_outlined, color: AppColors.dangerRed, size: 18),
                      SizedBox(width: 8),
                      Text('Delete All Stock', style: TextStyle(color: AppColors.dangerRed)),
                    ],
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
      body: Column(
        children: [
          // Filter Tabs
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg, vertical: AppSpacing.sm),
            child: Row(
              children: [
                _buildFilterChip('All Stock', 'all'),
                const SizedBox(width: AppSpacing.xs),
                _buildFilterChip('In Stock', 'in_stock'),
                const SizedBox(width: AppSpacing.xs),
                _buildFilterChip('Low Stock (≤10)', 'low_stock'),
                const SizedBox(width: AppSpacing.xs),
                _buildFilterChip('Expiring Soon (≤60d)', 'expiring'),
              ],
            ),
          ),

          const Divider(height: 1, color: AppColors.border),

          // Inventory List
          Expanded(
            child: filtered.isEmpty
                ? const Center(
                    child: Text('No inventory batches match this view', style: TextStyle(color: AppColors.textMuted)),
                  )
                : ListView.separated(
                    padding: const EdgeInsets.all(AppSpacing.lg),
                    itemCount: filtered.length,
                    separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.sm),
                    itemBuilder: (context, index) {
                      final item = filtered[index];
                      return _buildInventoryCard(item);
                    },
                  ),
          ),
        ],
      ),
      bottomNavigationBar: _isSelectMode && _selectedIds.isNotEmpty
          ? Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: const BoxDecoration(
                color: Colors.white,
                border: Border(top: BorderSide(color: AppColors.border)),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () {
                        setState(() {
                          _isSelectMode = false;
                          _selectedIds.clear();
                        });
                      },
                      child: const Text('Cancel'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: ElevatedButton.icon(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.dangerRed,
                        foregroundColor: Colors.white,
                      ),
                      icon: const Icon(Icons.delete_outline),
                      label: Text('Delete (${_selectedIds.length})'),
                      onPressed: _deleteSelected,
                    ),
                  ),
                ],
              ),
            )
          : null,
    );
  }

  Widget _buildFilterChip(String label, String key) {
    final bool isSelected = _activeFilter == key;
    return ChoiceChip(
      label: Text(label),
      selected: isSelected,
      selectedColor: const Color(0xFFF1F5F9),
      backgroundColor: AppColors.surfaceCard,
      side: BorderSide(
        color: isSelected ? AppColors.brandDeep : AppColors.border,
        width: 1,
      ),
      labelStyle: TextStyle(
        fontFamily: AppTypography.fontUi,
        fontSize: 12.5,
        fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
        color: isSelected ? AppColors.brandDeep : AppColors.textMuted,
      ),
      onSelected: (_) {
        setState(() {
          _activeFilter = key;
        });
      },
    );
  }

  Widget _buildInventoryCard(Map<String, dynamic> item) {
    final int id = item['id'] as int;
    final bool isChecked = _selectedIds.contains(id);

    BadgeStatus badgeStatus = BadgeStatus.safe;
    String badgeLabel = 'In Stock';

    if (item['days_left'] <= 0) {
      badgeStatus = BadgeStatus.danger;
      badgeLabel = 'Expired';
    } else if (item['days_left'] <= 60) {
      badgeStatus = BadgeStatus.warning;
      badgeLabel = 'Expiring (${item['days_left']}d)';
    }

    return InkWell(
      onLongPress: () => _toggleSelection(id),
      onTap: _isSelectMode ? () => _toggleSelection(id) : null,
      borderRadius: AppSpacing.roundedMd,
      child: Container(
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: BoxDecoration(
          color: isChecked ? const Color(0xFFFEF2F2) : AppColors.surfaceCard,
          borderRadius: AppSpacing.roundedMd,
          border: Border.all(
            color: isChecked ? AppColors.dangerRed : AppColors.border,
            width: isChecked ? 1.5 : 1,
          ),
          boxShadow: AppSpacing.shadowSubtle,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (_isSelectMode) ...[
              Checkbox(
                value: isChecked,
                activeColor: AppColors.dangerRed,
                onChanged: (_) => _toggleSelection(id),
              ),
              const SizedBox(width: 4),
            ],
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Expanded(
                        child: Text(
                          item['name'],
                          style: AppTypography.bodyMedium.copyWith(fontWeight: FontWeight.w600),
                        ),
                      ),
                      StatusBadge(label: badgeLabel, status: badgeStatus),
                    ],
                  ),
                  const SizedBox(height: AppSpacing.xs),
                  Row(
                    children: [
                      BatchBadge(batchNumber: item['batch']),
                      const SizedBox(width: AppSpacing.sm),
                      Text('Exp: ${item['expiry']}', style: AppTypography.numericDate),
                    ],
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  const Divider(height: 1, color: AppColors.border),
                  const SizedBox(height: AppSpacing.sm),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Row(
                        children: [
                          Text(
                            '${item['quantity']} ${item['unit']}s',
                            style: AppTypography.numericPrice,
                          ),
                          if (item['loose_stock'] > 0) ...[
                            const SizedBox(width: AppSpacing.xs),
                            Text(
                              '(+${item['loose_stock']} loose tabs)',
                              style: AppTypography.bodyMuted.copyWith(fontSize: 11),
                            ),
                          ],
                        ],
                      ),
                      TabularCurrency(
                        amount: item['mrp'],
                        style: AppTypography.numericPrice.copyWith(fontSize: 15),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
