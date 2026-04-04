import { useState } from 'react';
import { Copy, Check, ExternalLink, Eye } from 'lucide-react';
import type { LeadFormConfig } from '@/types';

interface LeadFormBuilderProps {
  form: LeadFormConfig;
  onUpdate: (id: string, updates: Partial<LeadFormConfig>) => void;
}

export function LeadFormBuilder({ form, onUpdate }: LeadFormBuilderProps) {
  const [copied, setCopied] = useState<'iframe' | 'url' | null>(null);
  const [editing, setEditing] = useState<Record<string, string>>({});

  const baseUrl = window.location.origin;
  const formUrl = `${baseUrl}/form/${form.slug}`;
  const iframeCode = `<iframe src="${formUrl}" width="100%" height="700" frameborder="0" style="border-radius:12px;"></iframe>`;

  const handleCopy = async (type: 'iframe' | 'url') => {
    const text = type === 'iframe' ? iframeCode : formUrl;
    await navigator.clipboard.writeText(text);
    setCopied(type);
    setTimeout(() => setCopied(null), 2000);
  };

  const handleFieldBlur = (field: string) => {
    const value = editing[field];
    if (value !== undefined && value !== (form as any)[field]) {
      onUpdate(form.id, { [field]: value });
    }
  };

  const field = (name: keyof LeadFormConfig) => (
    editing[name] !== undefined ? editing[name] : (form[name] as string) || ''
  );

  return (
    <div className="space-y-5">
      {/* Form fields editor */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Form Name</label>
          <input
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1B3A5C]/30"
            value={field('name')}
            onChange={(e) => setEditing((p) => ({ ...p, name: e.target.value }))}
            onBlur={() => handleFieldBlur('name')}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Slug (URL path)</label>
          <input
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1B3A5C]/30"
            value={field('slug')}
            onChange={(e) => setEditing((p) => ({ ...p, slug: e.target.value }))}
            onBlur={() => handleFieldBlur('slug')}
          />
        </div>
        <div className="md:col-span-2">
          <label className="block text-xs font-medium text-gray-600 mb-1">Headline</label>
          <input
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1B3A5C]/30"
            value={field('headline')}
            onChange={(e) => setEditing((p) => ({ ...p, headline: e.target.value }))}
            onBlur={() => handleFieldBlur('headline')}
          />
        </div>
        <div className="md:col-span-2">
          <label className="block text-xs font-medium text-gray-600 mb-1">Subheadline</label>
          <input
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1B3A5C]/30"
            value={field('subheadline')}
            onChange={(e) => setEditing((p) => ({ ...p, subheadline: e.target.value }))}
            onBlur={() => handleFieldBlur('subheadline')}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Brand Color</label>
          <div className="flex items-center gap-2">
            <input
              type="color"
              className="h-9 w-14 border border-gray-200 rounded-lg cursor-pointer"
              value={field('brand_color') || '#1B3A5C'}
              onChange={(e) => setEditing((p) => ({ ...p, brand_color: e.target.value }))}
              onBlur={() => handleFieldBlur('brand_color')}
            />
            <span className="text-sm text-gray-600">{field('brand_color') || '#1B3A5C'}</span>
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Status</label>
          <select
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
            value={form.active ? 'active' : 'inactive'}
            onChange={(e) => onUpdate(form.id, { active: e.target.value === 'active' })}
          >
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
        </div>
        <div className="md:col-span-2">
          <label className="block text-xs font-medium text-gray-600 mb-1">Thank You Message</label>
          <textarea
            rows={2}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1B3A5C]/30 resize-none"
            value={field('thank_you_message')}
            onChange={(e) => setEditing((p) => ({ ...p, thank_you_message: e.target.value }))}
            onBlur={() => handleFieldBlur('thank_you_message')}
          />
        </div>
      </div>

      {/* Embed codes */}
      <div className="border-t pt-5 space-y-3">
        <h4 className="text-sm font-semibold text-gray-800">Embed Options</h4>

        {/* Direct URL */}
        <div>
          <p className="text-xs text-gray-500 mb-1.5">Direct URL (share as Facebook ad destination, link-in-bio, etc.)</p>
          <div className="flex items-center gap-2">
            <code className="flex-1 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 text-xs text-gray-700 truncate">
              {formUrl}
            </code>
            <button
              onClick={() => handleCopy('url')}
              className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 transition-colors"
              title="Copy URL"
            >
              {copied === 'url' ? <Check className="h-4 w-4 text-green-600" /> : <Copy className="h-4 w-4 text-gray-500" />}
            </button>
            <a
              href={formUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 transition-colors"
              title="Preview form"
            >
              <ExternalLink className="h-4 w-4 text-gray-500" />
            </a>
          </div>
        </div>

        {/* iFrame */}
        <div>
          <p className="text-xs text-gray-500 mb-1.5">iFrame Embed (paste into any website or landing page)</p>
          <div className="flex items-start gap-2">
            <code className="flex-1 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 text-xs text-gray-700 break-all">
              {iframeCode}
            </code>
            <button
              onClick={() => handleCopy('iframe')}
              className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 transition-colors shrink-0"
              title="Copy embed code"
            >
              {copied === 'iframe' ? <Check className="h-4 w-4 text-green-600" /> : <Copy className="h-4 w-4 text-gray-500" />}
            </button>
          </div>
        </div>
      </div>

      {/* SMS confirmation toggle */}
      <div className="flex items-center gap-3 pt-2">
        <button
          onClick={() => onUpdate(form.id, { send_confirmation_sms: !form.send_confirmation_sms })}
          className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${form.send_confirmation_sms ? 'bg-[#1B3A5C]' : 'bg-gray-200'}`}
        >
          <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${form.send_confirmation_sms ? 'translate-x-4' : 'translate-x-0.5'}`} />
        </button>
        <span className="text-sm text-gray-700">Send SMS confirmation to seller on submit</span>
      </div>
    </div>
  );
}
