import { useState } from 'react';
import { useDeals, useUpdateDeal, useCreateDeal, type DealWrite } from '@/hooks/useDeals';
import { useLeads } from '@/hooks/useLeads';
import { useDealStore } from '@/stores/useDealStore';
import { KanbanColumn } from '@/components/pipeline/KanbanColumn';
import { Modal } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import type { Deal } from '@/types';
import { formatCurrency, daysUntil } from '@/lib/utils';
import { localDateString } from '@/lib/taskDates';
import { cn } from '@/lib/utils';
import {
  DndContext,
  type DragEndEvent,
  type DragStartEvent,
  PointerSensor,
  useSensor,
  useSensors,
  closestCorners,
  DragOverlay,
} from '@dnd-kit/core';
import { Plus } from 'lucide-react';
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
  const { data: deals = [], isLoading, error: dealsError, refetch } = useDeals();
  const updateDeal = useUpdateDeal();
  const createDeal = useCreateDeal();
  const { moveDealStage } = useDealStore();
  const [selectedDeal, setSelectedDeal] = useState<Deal | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [newDealOpen, setNewDealOpen] = useState(false);
  const [newDeal, setNewDeal] = useState<DealWrite>({ stage: 'offer_made' });
  const [leadSearch, setLeadSearch] = useState('');
  const [leadPage, setLeadPage] = useState(1);
  const { data: leadData, isLoading: leadsLoading, error: leadsError } = useLeads({ search: leadSearch, page: leadPage, pageSize: 50 });
  const [activeDragId, setActiveDragId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<DealWrite>({});

  // Read the same optimistic state that the columns display.
  const { deals: storedDeals } = useDealStore();
  const displayDeals = storedDeals.length > 0 ? storedDeals : deals;

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } })
  );

  const handleDragStart = (event: DragStartEvent) => {
    setActiveDragId(event.active.id as string);
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    setActiveDragId(null);
    if (updateDeal.isPending) return;
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const dealId = active.id as string;
    const targetId = over.id as string;
    const targetStage = COLUMNS.some((c) => c.id === targetId)
      ? targetId
      : displayDeals.find((d) => d.id === targetId)?.stage;
    if (!targetStage) return;

    const deal = displayDeals.find((d) => d.id === dealId);
    if (!deal || deal.stage === targetStage) return;

    // Optimistic update
    moveDealStage(dealId, targetStage);

    try {
      await updateDeal.mutateAsync({ id: dealId, updates: {
        stage: targetStage,
        ...(targetStage === 'closed' ? { actual_close_date: deal.actual_close_date || localDateString() }
          : deal.stage === 'closed' ? { actual_close_date: null } : {}),
      } });
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
      actual_close_date: deal.actual_close_date,
      notes: deal.notes,
      stage: deal.stage,
      title_company: deal.title_company,
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    if (!selectedDeal) return;
    try {
      await updateDeal.mutateAsync({ id: selectedDeal.id, updates: {
        ...editForm,
        actual_close_date: editForm.stage === 'closed'
          ? editForm.actual_close_date || localDateString()
          : null,
      } });
      setModalOpen(false);
    } catch {
      // Keep the draft open; the mutation reports the failed save.
    }
  };

  const handleCreateDeal = async () => {
    if (!newDeal.lead_id) {
      toast.error('Select the lead for this deal');
      return;
    }
    if (!newDeal.deal_name?.trim()) {
      toast.error('Enter a deal name (usually the property address)');
      return;
    }
    try {
      await createDeal.mutateAsync({
        ...newDeal,
        deal_name: newDeal.deal_name.trim(),
        ...(newDeal.stage === 'closed' ? { actual_close_date: localDateString() } : {}),
      });
      setNewDealOpen(false);
      setNewDeal({ stage: 'offer_made' });
      setLeadSearch('');
      setLeadPage(1);
    } catch {
      // Keep the form and selected lead available for retry.
    }
  };

  const activeDeal = activeDragId ? deals.find((d) => d.id === activeDragId) : null;

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
        <Button onClick={() => { setNewDeal({ stage: 'offer_made' }); setLeadSearch(''); setLeadPage(1); setNewDealOpen(true); }} icon={<Plus className="h-4 w-4" />}>
          New Deal
        </Button>
      </div>

      {dealsError ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4">
          <p role="alert" className="text-red-700">Unable to load deals: {dealsError.message}</p>
          <Button variant="outline" size="sm" onClick={() => void refetch()}>Retry</Button>
        </div>
      ) : isLoading ? (
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
          onDragCancel={() => setActiveDragId(null)}
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

      {/* New Deal Modal */}
      <Modal open={newDealOpen} onClose={() => setNewDealOpen(false)} title="New Deal" size="lg">
        <div className="p-6 space-y-4">
          <Input label="Find Lead" value={leadSearch}
            onChange={(e) => { setLeadSearch(e.target.value); setLeadPage(1); }} placeholder="Search address, owner or phone" />
          <Select label="Lead *" value={newDeal.lead_id || ''}
            onChange={(e) => {
              const lead = leadData?.data.find((item) => item.id === e.target.value);
              setNewDeal({ ...newDeal, lead_id: e.target.value,
                deal_name: lead?.property_address || newDeal.deal_name,
                contract_price: lead?.offer_price ?? lead?.mao ?? undefined,
                arv: lead?.estimated_arv, repair_estimate: lead?.estimated_repairs,
              });
            }}
            options={[
              ...(newDeal.lead_id && !leadData?.data.some((lead) => lead.id === newDeal.lead_id)
                ? [{ value: newDeal.lead_id, label: newDeal.deal_name || 'Selected lead' }] : []),
              ...(leadData?.data ?? []).map((lead) => ({ value: lead.id, label: `${lead.property_address}, ${lead.city}` })),
            ]} placeholder={leadsLoading ? 'Loading leads…' : 'Choose a lead'} />
          {leadsError && <p role="alert" className="text-sm text-red-600">Unable to load leads: {leadsError.message}</p>}
          {(leadData?.count ?? 0) > 50 && <div className="flex items-center gap-3 text-sm">
            <Button variant="outline" size="sm" disabled={leadPage === 1} onClick={() => setLeadPage((page) => page - 1)}>Previous leads</Button>
            <span>Page {leadPage} of {Math.ceil((leadData?.count ?? 0) / 50)}</span>
            <Button variant="outline" size="sm" disabled={leadPage * 50 >= (leadData?.count ?? 0)} onClick={() => setLeadPage((page) => page + 1)}>Next leads</Button>
          </div>}
          <Input label="Deal Name / Property Address" value={newDeal.deal_name || ''}
            onChange={(e) => setNewDeal({ ...newDeal, deal_name: e.target.value })}
            placeholder="e.g. 123 Main St, Dallas TX" />
          <div className="grid grid-cols-2 gap-4">
            <Select label="Stage" value={newDeal.stage || 'offer_made'}
              onChange={(e) => setNewDeal({ ...newDeal, stage: e.target.value })}
              options={COLUMNS.map((c) => ({ value: c.id, label: c.title }))} />
            <Input label="Contract Price" type="number" value={newDeal.contract_price || ''}
              onChange={(e) => setNewDeal({ ...newDeal, contract_price: Number(e.target.value) })} />
            <Input label="Assignment Fee" type="number" value={newDeal.assignment_fee || ''}
              onChange={(e) => setNewDeal({ ...newDeal, assignment_fee: Number(e.target.value) })} />
            <Input label="Closing Date" type="date" value={newDeal.closing_date || ''}
              onChange={(e) => setNewDeal({ ...newDeal, closing_date: e.target.value || null })} />
          </div>
          <Textarea label="Notes" value={newDeal.notes || ''} rows={2}
            onChange={(e) => setNewDeal({ ...newDeal, notes: e.target.value })} />
          <div className="flex justify-end gap-3">
            <Button variant="outline" onClick={() => setNewDealOpen(false)}>Cancel</Button>
            <Button onClick={handleCreateDeal} loading={createDeal.isPending} icon={<Plus className="h-4 w-4" />}>
              Create Deal
            </Button>
          </div>
        </div>
      </Modal>

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
                  onChange={(e) => setEditForm({ ...editForm, contract_date: e.target.value || null })} />
                <Input label="Closing Date" type="date"
                  value={editForm.closing_date || ''}
                  onChange={(e) => setEditForm({ ...editForm, closing_date: e.target.value || null })} />
                {editForm.stage === 'closed' && <Input label="Actual Close Date" type="date"
                  value={editForm.actual_close_date || localDateString()}
                  onChange={(e) => setEditForm({ ...editForm, actual_close_date: e.target.value || null })} />}
              </div>
              {editForm.closing_date && (
                <div className={cn(
                  'mt-2 text-sm font-medium',
                  daysUntil(editForm.closing_date) !== null && (daysUntil(editForm.closing_date) ?? 99) <= 7
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
