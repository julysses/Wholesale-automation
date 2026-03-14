import { useState } from 'react';
import { useDeals, useUpdateDeal, useCreateDeal } from '@/hooks/useDeals';
import { useDealStore } from '@/stores/useDealStore';
import { KanbanColumn } from '@/components/pipeline/KanbanColumn';
import { Modal } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import type { Deal } from '@/types';
import { formatCurrency, formatDate, daysUntil, getStageLabel } from '@/lib/utils';
import { cn } from '@/lib/utils';
import {
  DndContext,
  type DragEndEvent,
  type DragOverEvent,
  type DragStartEvent,
  PointerSensor,
  useSensor,
  useSensors,
  closestCorners,
  DragOverlay,
} from '@dnd-kit/core';
import { Plus, X, Calendar, DollarSign } from 'lucide-react';
import { toast } from 'sonner';

const COLUMNS = [
  { id: 'offer_made', title: 'Offer Made', color: 'blue-500' },
  { id: 'under_contract', title: 'Under Contract', color: 'orange-500' },
  { id: 'marketing_to_buyers', title: 'Marketing to Buyers', color: 'purple-500' },
  { id: 'buyer_found', title: 'Buyer Found', color: 'yellow-500' },
  { id: 'assigned', title: 'Assigned', color: 'teal-500' },
  { id: 'closed', title: 'Closed', color: 'green-500' },
];

export function Pipeline() {
  const { data: deals = [], isLoading } = useDeals();
  const updateDeal = useUpdateDeal();
  const { moveDealStage } = useDealStore();
  const [selectedDeal, setSelectedDeal] = useState<Deal | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [activeDragId, setActiveDragId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<Partial<Deal>>({});

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } })
  );

  const handleDragStart = (event: DragStartEvent) => {
    setActiveDragId(event.active.id as string);
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    setActiveDragId(null);
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const dealId = active.id as string;
    const targetStage = over.id as string;

    // Only move if dropped on a column (not another card)
    const isColumn = COLUMNS.some((c) => c.id === targetStage);
    if (!isColumn) return;

    const deal = deals.find((d) => d.id === dealId);
    if (!deal || deal.stage === targetStage) return;

    // Optimistic update
    moveDealStage(dealId, targetStage);

    try {
      await updateDeal.mutateAsync({ id: dealId, updates: { stage: targetStage } });
    } catch {
      // Rollback
      moveDealStage(dealId, deal.stage);
      toast.error('Failed to move deal');
    }
  };

  const handleDealClick = (deal: Deal) => {
    setSelectedDeal(deal);
    setEditForm({
      deal_name: deal.deal_name,
      contract_price: deal.contract_price,
      arv: deal.arv,
      repair_estimate: deal.repair_estimate,
      assignment_fee: deal.assignment_fee,
      buyer_price: deal.buyer_price,
      closing_date: deal.closing_date,
      contract_date: deal.contract_date,
      notes: deal.notes,
      stage: deal.stage,
      title_company: deal.title_company,
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    if (!selectedDeal) return;
    await updateDeal.mutateAsync({ id: selectedDeal.id, updates: editForm });
    setModalOpen(false);
  };

  const activeDeal = activeDragId ? deals.find((d) => d.id === activeDragId) : null;

  // Use stored deals for optimistic updates
  const { deals: storedDeals } = useDealStore();
  const displayDeals = storedDeals.length > 0 ? storedDeals : deals;

  const pipelineDeals = displayDeals.filter((d) => !['cancelled'].includes(d.stage));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Pipeline</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {pipelineDeals.length} active deals ·{' '}
            {formatCurrency(pipelineDeals.reduce((s, d) => s + (d.assignment_fee || 0), 0))} in fees
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex gap-4 overflow-x-auto pb-4">
          {COLUMNS.map((col) => (
            <div key={col.id} className="w-72 shrink-0 h-64 bg-gray-100 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCorners}
          onDragStart={handleDragStart}
          onDragEnd={handleDragEnd}
        >
          <div className="flex gap-4 overflow-x-auto pb-4">
            {COLUMNS.map((col) => (
              <KanbanColumn
                key={col.id}
                id={col.id}
                title={col.title}
                color={col.color}
                deals={pipelineDeals.filter((d) => d.stage === col.id)}
                onDealClick={handleDealClick}
              />
            ))}
          </div>

          <DragOverlay>
            {activeDeal && (
              <div className="bg-white rounded-lg border-2 border-[#1B3A5C] shadow-2xl p-3 w-72 rotate-2">
                <p className="font-semibold text-sm text-gray-900 truncate">
                  {activeDeal.lead?.property_address || activeDeal.deal_name}
                </p>
                <p className="text-xs text-gray-400">{formatCurrency(activeDeal.contract_price)}</p>
              </div>
            )}
          </DragOverlay>
        </DndContext>
      )}

      {/* Deal Detail Modal */}
      {selectedDeal && (
        <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Deal Details" size="xl">
          <div className="p-6 space-y-6">
            {/* Header info */}
            <div className="bg-[#1B3A5C] rounded-xl p-4 text-white">
              <h3 className="text-lg font-semibold">
                {selectedDeal.lead?.property_address || selectedDeal.deal_name}
              </h3>
              <p className="text-sm opacity-70 mt-0.5">
                {selectedDeal.lead?.city}, {selectedDeal.lead?.state} {selectedDeal.lead?.zip_code}
              </p>
              <div className="flex gap-4 mt-3">
                <Select
                  value={editForm.stage || selectedDeal.stage}
                  onChange={(e) => setEditForm({ ...editForm, stage: e.target.value })}
                  options={COLUMNS.map((c) => ({ value: c.id, label: c.title }))}
                  className="text-gray-900"
                />
              </div>
            </div>

            {/* Financials */}
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-3">Financials</h4>
              <div className="grid grid-cols-2 gap-4">
                <Input label="Contract Price" type="number"
                  value={editForm.contract_price || ''}
                  onChange={(e) => setEditForm({ ...editForm, contract_price: Number(e.target.value) })} />
                <Input label="ARV" type="number"
                  value={editForm.arv || ''}
                  onChange={(e) => setEditForm({ ...editForm, arv: Number(e.target.value) })} />
                <Input label="Repair Estimate" type="number"
                  value={editForm.repair_estimate || ''}
                  onChange={(e) => setEditForm({ ...editForm, repair_estimate: Number(e.target.value) })} />
                <Input label="Assignment Fee" type="number"
                  value={editForm.assignment_fee || ''}
                  onChange={(e) => setEditForm({ ...editForm, assignment_fee: Number(e.target.value) })} />
                <Input label="Buyer Price" type="number"
                  value={editForm.buyer_price || ''}
                  onChange={(e) => setEditForm({ ...editForm, buyer_price: Number(e.target.value) })} />
              </div>
            </div>

            {/* Dates */}
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-3">Dates</h4>
              <div className="grid grid-cols-2 gap-4">
                <Input label="Contract Date" type="date"
                  value={editForm.contract_date || ''}
                  onChange={(e) => setEditForm({ ...editForm, contract_date: e.target.value })} />
                <Input label="Closing Date" type="date"
                  value={editForm.closing_date || ''}
                  onChange={(e) => setEditForm({ ...editForm, closing_date: e.target.value })} />
              </div>
              {editForm.closing_date && (
                <div className={cn(
                  'mt-2 text-sm font-medium',
                  daysUntil(editForm.closing_date) !== null && (daysUntil(editForm.closing_date) || 99) <= 7
                    ? 'text-red-600' : 'text-gray-500'
                )}>
                  {(() => {
                    const d = daysUntil(editForm.closing_date);
                    if (d === null) return '';
                    if (d < 0) return `${Math.abs(d)} days past closing`;
                    if (d === 0) return 'Closing today';
                    return `Closes in ${d} days`;
                  })()}
                </div>
              )}
            </div>

            {/* Title */}
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-3">Title Company</h4>
              <Input label="Company Name" value={editForm.title_company || ''}
                onChange={(e) => setEditForm({ ...editForm, title_company: e.target.value })} />
            </div>

            {/* Notes */}
            <Textarea label="Notes" value={editForm.notes || ''}
              onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })} rows={3} />

            <div className="flex justify-end gap-3">
              <Button variant="outline" onClick={() => setModalOpen(false)}>Cancel</Button>
              <Button onClick={handleSave} loading={updateDeal.isPending}>Save Changes</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
