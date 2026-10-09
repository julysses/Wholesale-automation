/**
 * /form/:formId — PUBLIC multi-step lead qualification form.
 * No auth required. No Layout wrapper.
 * Mobile-first, large tap targets, 4 steps.
 */

import { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { Loader2, ChevronRight, ChevronLeft, CheckCircle, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { clearPublicIntake, matchesPublicIntakeReceipt, preservePublicIntake, readPublicIntake, UNCONFIRMED_INQUIRY, type PendingPublicIntake } from '@/lib/publicIntakeRecovery';

// ── Types ──────────────────────────────────────────────────────────────────────
interface FormQuestion {
  id: string;
  step: number;
  type: 'text' | 'tel' | 'email' | 'number' | 'radio' | 'checkbox';
  field_name: string;
  label: string;
  placeholder?: string;
  required: boolean;
  options?: { value: string; label: string; score_hint?: number }[];
}

interface FormConfig {
  id: string;
  name: string;
  slug: string;
  headline: string;
  subheadline?: string;
  brand_color: string;
  logo_url?: string;
  thank_you_message: string;
  questions: FormQuestion[];
}

// ── Helpers ────────────────────────────────────────────────────────────────────
const groupByStep = (questions: FormQuestion[]) => {
  const steps: Record<number, FormQuestion[]> = {};
  for (const q of questions) {
    if (!steps[q.step]) steps[q.step] = [];
    steps[q.step].push(q);
  }
  return steps;
};

export function LeadForm() {
  const { formId } = useParams<{ formId: string }>();
  return <LeadFormInner key={formId} formId={formId || ''} />;
}

function LeadFormInner({ formId }: { formId: string }) {
  const [recovery] = useState(() => {
    try { return { draft: readPublicIntake(window.sessionStorage, formId), blocked: false }; }
    catch { return { draft: null, blocked: true }; }
  });
  const [pending, setPending] = useState<PendingPublicIntake | null>(recovery.draft);
  const [blocked, setBlocked] = useState(recovery.blocked);
  const busy = useRef(false);
  const [config, setConfig] = useState<FormConfig | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadAttempt, setLoadAttempt] = useState(0);

  const [currentStep, setCurrentStep] = useState(1);
  const [answers, setAnswers] = useState<Record<string, string>>(recovery.draft?.answers || {});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Fetch form config
  useEffect(() => {
    if (!formId) return;
    const controller = new AbortController();
    let active = true;
    const timeout = window.setTimeout(() => controller.abort(), 15000);
    setLoading(true);
    setLoadError(null);
    setConfig(null);
    fetch(`/api/forms/${encodeURIComponent(formId)}`, { signal: controller.signal })
      .then(async (r) => {
        if (!r.ok) throw new Error(r.status === 404
          ? 'This form was not found or is no longer active.'
          : 'We could not load the form right now. Please try again.');
        return r.json();
      })
      .then((data) => {
        if (!active) return;
        setConfig(data);
      })
      .catch((e) => {
        if (!active) return;
        setLoadError(e.name === 'AbortError' || e instanceof TypeError
          ? 'The connection is taking too long or is unavailable. Please try again.'
          : e.message || 'We could not load the form right now. Please try again.');
      })
      .finally(() => {
        window.clearTimeout(timeout);
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [formId, loadAttempt]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (loadError || !config) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-6">
        <div className="text-center max-w-md">
          <AlertTriangle className="h-12 w-12 text-yellow-500 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-gray-900 mb-2">Form Not Available</h2>
          <p role="alert" className="text-gray-600 text-sm">
            {loadError || 'We could not load the form right now. Please try again.'}
          </p>
          <button type="button" onClick={() => setLoadAttempt((attempt) => attempt + 1)}
            className="mt-4 rounded-lg bg-gray-900 px-5 py-3 text-sm font-medium text-white">
            Try again
          </button>
        </div>
      </div>
    );
  }

  const brandColor = config.brand_color || '#1B3A5C';
  const stepGroups = groupByStep(config.questions);
  const totalSteps = Math.max(...Object.keys(stepGroups).map(Number), 1);
  const currentQuestions = stepGroups[currentStep] || [];
  const progress = ((currentStep - 1) / totalSteps) * 100;

  const validate = (step: number) => {
    const errs: Record<string, string> = {};
    for (const q of stepGroups[step] || []) {
      if (q.required && (q.type === 'checkbox' ? answers[q.field_name] !== 'true' : !answers[q.field_name]?.trim())) {
        errs[q.field_name] = 'This field is required';
      }
      if (q.type === 'tel' && answers[q.field_name]) {
        const digits = answers[q.field_name].replace(/\D/g, '');
        if (digits.length < 10) errs[q.field_name] = 'Enter a valid phone number';
      }
    }
    return errs;
  };

  const handleNext = () => {
    const errs = pending ? {} : validate(currentStep);
    if (Object.keys(errs).length > 0) {
      setErrors(errs);
      return;
    }
    setErrors({});
    setCurrentStep((s) => s + 1);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleBack = () => {
    setCurrentStep((s) => s - 1);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleSubmit = async () => {
    if (busy.current || blocked) return;
    const errs = pending ? {} : validate(currentStep);
    if (Object.keys(errs).length > 0) {
      setErrors(errs);
      return;
    }

    busy.current = true;
    let draft: PendingPublicIntake | null;
    let firstAttempt = false;
    try {
      draft = readPublicIntake(window.sessionStorage, formId);
      firstAttempt = draft === null;
      if (!draft) {
        const params = new URLSearchParams(window.location.search);
        draft = preservePublicIntake(window.sessionStorage, {
          version: 1, formId, createdAt: new Date().toISOString(), answers: { ...answers },
          payload: {
            request_id: crypto.randomUUID(),
            answers: {
              ...answers,
              sms_consent_text: config.questions.find(q => q.field_name === 'sms_opt_in' && q.type === 'checkbox')?.label || '',
              sms_consent_source: window.location.origin + window.location.pathname,
            },
            utm_source: params.get('utm_source'), utm_medium: params.get('utm_medium'), utm_campaign: params.get('utm_campaign'),
          },
        });
      }
    } catch {
      busy.current = false;
      setBlocked(true);
      setSubmitError('This browser cannot safely save or recover your inquiry. Contact our team before submitting again.');
      return;
    }
    setPending(draft);
    setAnswers(draft.answers);
    setSubmitting(true);
    setSubmitError(null);
    try {
      const resp = await fetch(`/api/forms/${encodeURIComponent(formId)}/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(draft.payload),
        signal: AbortSignal.timeout(45000),
      });
      const data = await resp.json();
      if (!resp.ok || !matchesPublicIntakeReceipt(data, draft)) {
        if (firstAttempt && (resp.status === 400 || resp.status === 422)) {
          clearPublicIntake(window.sessionStorage, draft);
          setPending(null);
          setSubmitError(typeof data.detail === 'string' ? data.detail : 'Please check your contact details and try again.');
        } else {
          setSubmitError(UNCONFIRMED_INQUIRY);
        }
        return;
      }
      try { clearPublicIntake(window.sessionStorage, draft); } catch {
        // A confirmed receipt remains success; retained recovery safely replays.
      }
      setSubmitted(true);
      if (typeof data.redirect_url === 'string' && data.redirect_url) {
        try {
          const target = new URL(data.redirect_url, window.location.origin);
          if ((target.protocol === 'https:' || target.origin === window.location.origin) && !target.username && !target.password) window.location.href = target.href;
        } catch { /* Keep the confirmed receipt visible for an invalid redirect. */ }
      }
    } catch {
      setSubmitError(UNCONFIRMED_INQUIRY);
    } finally {
      busy.current = false;
      setSubmitting(false);
    }
  };

  // ── Success screen ──────────────────────────────────────────────────────────
  if (submitted) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6" style={{ backgroundColor: `${brandColor}10` }}>
        <div className="bg-white rounded-2xl shadow-lg p-8 max-w-md w-full text-center">
          <CheckCircle className="h-14 w-14 mx-auto mb-4" style={{ color: brandColor }} />
          <h2 className="text-2xl font-bold text-gray-900 mb-3">You're All Set!</h2>
          <p className="text-gray-600 leading-relaxed">{config.thank_you_message}</p>
          {pending && <p className="text-xs text-gray-500 mt-4">Inquiry reference: {pending.payload.request_id}</p>}
        </div>
      </div>
    );
  }

  // ── Form ────────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen" style={{ backgroundColor: `${brandColor}08` }}>
      {/* Header */}
      <div className="py-6 px-6 text-center" style={{ backgroundColor: brandColor }}>
        {config.logo_url && (
          <img src={config.logo_url} alt="Logo" className="h-10 mx-auto mb-3" />
        )}
        <h1 className="text-xl md:text-2xl font-bold text-white">{config.headline}</h1>
        {config.subheadline && (
          <p className="text-sm text-white/80 mt-1 max-w-sm mx-auto">{config.subheadline}</p>
        )}
      </div>

      {/* Progress bar */}
      <div className="h-1.5 bg-gray-200">
        <div
          className="h-full transition-all duration-500"
          style={{ width: `${progress}%`, backgroundColor: brandColor }}
        />
      </div>

      {/* Step indicator */}
      <div className="text-center py-3">
        <span className="text-xs text-gray-500">Step {currentStep} of {totalSteps}</span>
      </div>

      {/* Form body */}
      <div className="max-w-lg mx-auto px-4 pb-12">
        <div className="bg-white rounded-2xl shadow-sm p-6 space-y-5">
          <fieldset disabled={blocked || !!pending || submitting} className="space-y-5">
          {currentQuestions.map((q) => (
            <QuestionField
              key={q.id}
              question={q}
              value={answers[q.field_name] || ''}
              error={errors[q.field_name]}
              brandColor={brandColor}
              onChange={(val) => {
                setAnswers((prev) => ({ ...prev, [q.field_name]: val }));
                if (errors[q.field_name]) setErrors((e) => ({ ...e, [q.field_name]: '' }));
              }}
            />
          ))}
          </fieldset>

          {(submitError || blocked || (pending && !submitting)) && (
            <div role="alert" className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              {submitError || (blocked ? 'This browser cannot recover a previous inquiry. Contact our team before submitting again.' : UNCONFIRMED_INQUIRY)}
            </div>
          )}
          {pending && !submitted && <div className="space-y-3">
            <p className="text-xs text-gray-500">Saved inquiry reference: {pending.payload.request_id}. Original answers remain locked while we confirm receipt.</p>
            <button type="button" onClick={handleSubmit} disabled={blocked || submitting} style={{ backgroundColor: brandColor }} className="w-full rounded-xl px-4 py-3 text-white text-sm font-semibold disabled:opacity-60">{submitting ? 'Confirming your inquiry…' : 'Retry Saved Inquiry'}</button>
          </div>}

          {/* Navigation */}
          <div className="flex gap-3 pt-2">
            {currentStep > 1 && (
              <button
                onClick={handleBack}
                disabled={submitting}
                className="flex items-center gap-1 px-4 py-3 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors"
              >
                <ChevronLeft className="h-4 w-4" /> Back
              </button>
            )}
            {currentStep < totalSteps ? (
              <button
                onClick={handleNext}
                disabled={blocked || submitting}
                className="flex-1 flex items-center justify-center gap-1 py-3 rounded-xl text-sm font-semibold text-white transition-colors"
                style={{ backgroundColor: brandColor }}
              >
                Next <ChevronRight className="h-4 w-4" />
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                disabled={blocked || submitting || !!pending}
                className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-semibold text-white transition-colors disabled:opacity-60"
                style={{ backgroundColor: brandColor }}
              >
                {submitting ? (
                  <><Loader2 className="h-4 w-4 animate-spin" /> Submitting…</>
                ) : (
                  <>Get My Cash Offer <ChevronRight className="h-4 w-4" /></>
                )}
              </button>
            )}
          </div>
        </div>

        <p className="text-center text-xs text-gray-400 mt-4">
          We use your information to respond to your inquiry.
        </p>
      </div>
    </div>
  );
}

// ── Individual question renderer ───────────────────────────────────────────────
function QuestionField({
  question,
  value,
  error,
  brandColor,
  onChange,
}: {
  question: FormQuestion;
  value: string;
  error?: string;
  brandColor: string;
  onChange: (val: string) => void;
}) {
  const baseInput = cn(
    'w-full border rounded-xl px-4 py-3 text-sm focus:outline-none transition-colors',
    error ? 'border-red-400 focus:ring-2 focus:ring-red-200' : 'border-gray-200 focus:border-current'
  );

  if (question.type === 'radio' && question.options) {
    return (
      <div>
        <label className="block text-sm font-semibold text-gray-800 mb-3">
          {question.label}
          {question.required && <span className="text-red-400 ml-1">*</span>}
        </label>
        <div className="space-y-2">
          {question.options.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => onChange(opt.value)}
              className={cn(
                'w-full text-left px-4 py-3 rounded-xl border text-sm font-medium transition-all',
                value === opt.value
                  ? 'border-current text-white'
                  : 'border-gray-200 text-gray-700 hover:border-gray-300 bg-white'
              )}
              style={value === opt.value ? { backgroundColor: brandColor, borderColor: brandColor } : {}}
            >
              {opt.label}
            </button>
          ))}
        </div>
        {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
      </div>
    );
  }

  if (question.type === 'checkbox') {
    return (
      <label className="flex items-start gap-3 cursor-pointer">
        <input
          type="checkbox"
          checked={value === 'true'}
          onChange={(e) => onChange(e.target.checked ? 'true' : 'false')}
          className="mt-0.5 h-4 w-4 rounded"
          style={{ accentColor: brandColor }}
        />
        <span className="text-sm text-gray-700">{question.label}{error && <span className="block text-xs text-red-500 mt-1">{error}</span>}</span>
      </label>
    );
  }

  return (
    <div>
      <label htmlFor={`question-${question.id}`} className="block text-sm font-semibold text-gray-800 mb-2">
        {question.label}
        {question.required && <span className="text-red-400 ml-1">*</span>}
      </label>
      <input
        id={`question-${question.id}`}
        type={question.type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={question.placeholder || ''}
        className={baseInput}
        inputMode={question.type === 'tel' ? 'tel' : question.type === 'number' ? 'decimal' : 'text'}
        style={{ borderColor: value ? brandColor : undefined }}
      />
      {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
    </div>
  );
}
