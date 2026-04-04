/**
 * /form/:formId — PUBLIC multi-step lead qualification form.
 * No auth required. No Layout wrapper.
 * Mobile-first, large tap targets, 4 steps.
 */

import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Loader2, ChevronRight, ChevronLeft, CheckCircle, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';

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
  const [config, setConfig] = useState<FormConfig | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [currentStep, setCurrentStep] = useState(1);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Fetch form config
  useEffect(() => {
    if (!formId) return;
    fetch(`/api/forms/${formId}`)
      .then(async (r) => {
        if (!r.ok) throw new Error('Form not found');
        return r.json();
      })
      .then((data) => {
        setConfig(data);
        setLoading(false);
      })
      .catch((e) => {
        setLoadError(e.message || 'Failed to load form');
        setLoading(false);
      });
  }, [formId]);

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
          <p className="text-gray-600 text-sm">
            This form is not available right now. Please call us directly for assistance.
          </p>
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
      if (q.required && !answers[q.field_name]) {
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
    const errs = validate(currentStep);
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
    const errs = validate(currentStep);
    if (Object.keys(errs).length > 0) {
      setErrors(errs);
      return;
    }

    setSubmitting(true);
    setSubmitError(null);

    // UTM params from URL
    const params = new URLSearchParams(window.location.search);

    try {
      const resp = await fetch(`/api/forms/${formId}/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          answers,
          utm_source: params.get('utm_source'),
          utm_medium: params.get('utm_medium'),
          utm_campaign: params.get('utm_campaign'),
        }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || 'Submission failed');
      if (data.redirect_url) {
        window.location.href = data.redirect_url;
      } else {
        setSubmitted(true);
      }
    } catch (e: any) {
      setSubmitError(e.message || 'Something went wrong. Please call us directly.');
    } finally {
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

          {submitError && (
            <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              {submitError}
            </div>
          )}

          {/* Navigation */}
          <div className="flex gap-3 pt-2">
            {currentStep > 1 && (
              <button
                onClick={handleBack}
                className="flex items-center gap-1 px-4 py-3 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors"
              >
                <ChevronLeft className="h-4 w-4" /> Back
              </button>
            )}
            {currentStep < totalSteps ? (
              <button
                onClick={handleNext}
                className="flex-1 flex items-center justify-center gap-1 py-3 rounded-xl text-sm font-semibold text-white transition-colors"
                style={{ backgroundColor: brandColor }}
              >
                Next <ChevronRight className="h-4 w-4" />
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                disabled={submitting}
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
          Your information is secure and will never be shared or sold.
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
        <span className="text-sm text-gray-700">{question.label}</span>
      </label>
    );
  }

  return (
    <div>
      <label className="block text-sm font-semibold text-gray-800 mb-2">
        {question.label}
        {question.required && <span className="text-red-400 ml-1">*</span>}
      </label>
      <input
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
