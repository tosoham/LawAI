/**
 * DraftForm Component
 * Form for drafting legal documents
 */

import React, { useState } from 'react';
import { useDocuments } from '@/hooks/useDocuments';
import LoadingSpinner from '@/components/shared/LoadingSpinner';
import ErrorMessage from '@/components/shared/ErrorMessage';
import ReactMarkdown from 'react-markdown';

const DOCUMENT_TYPES = [
  { value: 'bail_application', label: 'Bail Application' },
  { value: 'petition', label: 'Petition' },
  { value: 'notice', label: 'Legal Notice' },
  { value: 'affidavit', label: 'Affidavit' },
] as const;

interface FormField {
  name: string;
  label: string;
  type: 'text' | 'textarea' | 'date' | 'select';
  options?: string[];
  required?: boolean;
  placeholder?: string;
}

const DOCUMENT_FIELDS: Record<string, FormField[]> = {
  bail_application: [
    { name: 'accused_name', label: 'Accused Name', type: 'text', required: true, placeholder: 'Full name of the accused' },
    { name: 'case_number', label: 'Case Number', type: 'text', required: true, placeholder: 'FIR/Case number' },
    { name: 'offense', label: 'Offense', type: 'text', required: true, placeholder: 'Section and offense details' },
    { name: 'court_name', label: 'Court Name', type: 'text', required: true, placeholder: 'Name of the court' },
    { name: 'grounds', label: 'Grounds for Bail', type: 'textarea', required: true, placeholder: 'Reasons for granting bail' },
    { name: 'arrest_date', label: 'Date of Arrest', type: 'date', required: false },
  ],
  petition: [
    { name: 'petitioner_name', label: 'Petitioner Name', type: 'text', required: true, placeholder: 'Name of petitioner' },
    { name: 'respondent_name', label: 'Respondent Name', type: 'text', required: true, placeholder: 'Name of respondent' },
    { name: 'court_name', label: 'Court Name', type: 'text', required: true, placeholder: 'Name of the court' },
    { name: 'subject', label: 'Subject Matter', type: 'text', required: true, placeholder: 'Brief subject of petition' },
    { name: 'facts', label: 'Facts of the Case', type: 'textarea', required: true, placeholder: 'Detailed facts' },
    { name: 'relief_sought', label: 'Relief Sought', type: 'textarea', required: true, placeholder: 'What relief is being requested' },
  ],
  notice: [
    { name: 'sender_name', label: 'Sender Name', type: 'text', required: true, placeholder: 'Your name/client name' },
    { name: 'recipient_name', label: 'Recipient Name', type: 'text', required: true, placeholder: 'Name of recipient' },
    { name: 'subject', label: 'Subject', type: 'text', required: true, placeholder: 'Subject of notice' },
    { name: 'issue', label: 'Issue/Grievance', type: 'textarea', required: true, placeholder: 'Describe the issue' },
    { name: 'demand', label: 'Demand/Action Required', type: 'textarea', required: true, placeholder: 'What action is demanded' },
    { name: 'deadline', label: 'Response Deadline', type: 'date', required: false },
  ],
  affidavit: [
    { name: 'deponent_name', label: 'Deponent Name', type: 'text', required: true, placeholder: 'Name of person making affidavit' },
    { name: 'case_number', label: 'Case Number', type: 'text', required: false, placeholder: 'Related case number (if any)' },
    { name: 'purpose', label: 'Purpose', type: 'text', required: true, placeholder: 'Purpose of affidavit' },
    { name: 'facts', label: 'Facts/Statements', type: 'textarea', required: true, placeholder: 'Statements to be affirmed' },
  ],
};

export const DraftForm: React.FC = () => {
  const [documentType, setDocumentType] = useState<typeof DOCUMENT_TYPES[number]['value']>('bail_application');
  const [formData, setFormData] = useState<Record<string, string>>({});
  const [showPreview, setShowPreview] = useState(false);

  const { draftedDocument, isLoading, error, draft, downloadDocx, reset } = useDocuments();

  const currentFields = DOCUMENT_FIELDS[documentType];

  const handleFieldChange = (name: string, value: string) => {
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Validate required fields
    const missingFields = currentFields
      .filter((field) => field.required && !formData[field.name]?.trim())
      .map((field) => field.label);

    if (missingFields.length > 0) {
      alert(`Please fill in required fields: ${missingFields.join(', ')}`);
      return;
    }

    await draft({
      document_type: documentType,
      case_details: formData,
    });
    setShowPreview(true);
  };

  const handleDownload = async () => {
    if (!draftedDocument) return;
    
    const filename = `${documentType}_${Date.now()}`;
    await downloadDocx(draftedDocument.document, filename);
  };

  const handleReset = () => {
    setFormData({});
    setShowPreview(false);
    reset();
  };

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <h2 className="text-xl font-semibold text-gray-900">Draft Legal Document</h2>
        <p className="text-sm text-gray-600">Generate professional legal documents</p>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-6 py-6">
          {!showPreview ? (
            /* Form View */
            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Document Type Selection */}
              <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                <label htmlFor="documentType" className="block text-sm font-medium text-gray-700 mb-2">
                  Document Type
                </label>
                <select
                  id="documentType"
                  value={documentType}
                  onChange={(e) => {
                    setDocumentType(e.target.value as typeof documentType);
                    setFormData({});
                  }}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                >
                  {DOCUMENT_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Dynamic Form Fields */}
              <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 space-y-4">
                <h3 className="text-lg font-medium text-gray-900 mb-4">Document Details</h3>
                
                {currentFields.map((field) => (
                  <div key={field.name}>
                    <label htmlFor={field.name} className="block text-sm font-medium text-gray-700 mb-2">
                      {field.label}
                      {field.required && <span className="text-red-500 ml-1">*</span>}
                    </label>
                    
                    {field.type === 'textarea' ? (
                      <textarea
                        id={field.name}
                        value={formData[field.name] || ''}
                        onChange={(e) => handleFieldChange(field.name, e.target.value)}
                        placeholder={field.placeholder}
                        rows={4}
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                      />
                    ) : field.type === 'select' && field.options ? (
                      <select
                        id={field.name}
                        value={formData[field.name] || ''}
                        onChange={(e) => handleFieldChange(field.name, e.target.value)}
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                      >
                        <option value="">Select...</option>
                        {field.options.map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        id={field.name}
                        type={field.type}
                        value={formData[field.name] || ''}
                        onChange={(e) => handleFieldChange(field.name, e.target.value)}
                        placeholder={field.placeholder}
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                      />
                    )}
                  </div>
                ))}
              </div>

              {error && <ErrorMessage message={error} />}

              {/* Submit Button */}
              <div className="flex space-x-4">
                <button
                  type="submit"
                  disabled={isLoading}
                  className="flex-1 px-6 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors font-medium"
                >
                  {isLoading ? <LoadingSpinner size="sm" text="Generating..." /> : 'Generate Document'}
                </button>
                <button
                  type="button"
                  onClick={handleReset}
                  className="px-6 py-3 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
                >
                  Reset
                </button>
              </div>
            </form>
          ) : (
            /* Preview View */
            <div className="space-y-6">
              <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-medium text-gray-900">Document Preview</h3>
                  <div className="flex space-x-2">
                    <button
                      onClick={handleDownload}
                      disabled={isLoading}
                      className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
                    >
                      <svg className="mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                      </svg>
                      Download .docx
                    </button>
                    <button
                      onClick={() => setShowPreview(false)}
                      className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
                    >
                      Edit
                    </button>
                  </div>
                </div>

                {draftedDocument && (
                  <div className="prose prose-sm max-w-none bg-gray-50 p-6 rounded-lg border border-gray-200">
                    <ReactMarkdown>{draftedDocument.document}</ReactMarkdown>
                  </div>
                )}
              </div>

              <button
                onClick={handleReset}
                className="w-full px-6 py-3 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
              >
                Create New Document
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default DraftForm;

// Made with Bob
