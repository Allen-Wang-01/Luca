import { useRef, useState } from 'react'
import type { DragEvent } from 'react'
import './PdfUploader.css'

const MAX_PDF_SIZE_BYTES = 25 * 1024 * 1024 // keep in sync with backend MAX_PDF_SIZE_BYTES

interface PdfUploaderProps {
  onFileSelected: (file: File) => void
  disabled?: boolean
}

function validatePdf(file: File): string | null {
  const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
  if (!isPdf) {
    return 'Please select a PDF file.'
  }
  if (file.size > MAX_PDF_SIZE_BYTES) {
    return 'File exceeds the 25MB size limit.'
  }
  return null
}

export function PdfUploader({ onFileSelected, disabled }: PdfUploaderProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [validationError, setValidationError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = (file: File) => {
    const error = validatePdf(file)
    setValidationError(error)
    if (!error) {
      setSelectedFile(file)
    }
  }

  const handleRemove = () => {
    setSelectedFile(null)
    setValidationError(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setIsDragging(false)
    if (disabled) return
    const file = event.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  const dropzoneClassName = [
    'uploader__dropzone',
    isDragging && 'uploader__dropzone--dragging',
    disabled && 'uploader__dropzone--disabled',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className="uploader">
      <div
        className={dropzoneClassName}
        onDragEnter={(e) => {
          e.preventDefault()
          if (!disabled) setIsDragging(true)
        }}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={(e) => {
          e.preventDefault()
          setIsDragging(false)
        }}
        onDrop={handleDrop}
        onClick={() => !disabled && inputRef.current?.click()}
        role="button"
        tabIndex={disabled ? -1 : 0}
      >
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          hidden
          disabled={disabled}
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) handleFile(file)
            e.target.value = ''
          }}
        />
        <svg
          className="uploader__icon"
          width="28"
          height="28"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          aria-hidden="true"
        >
          <path d="M12 15.5V4m0 0-3.5 3.5M12 4l3.5 3.5" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M4.5 15.5v2a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <p className="uploader__prompt">Drag and drop a financial report PDF here, or click to browse.</p>
        <p className="uploader__hint">PDF up to 25MB</p>
        {selectedFile && (
          <p className="uploader__filename">
            {selectedFile.name}
            <button
              type="button"
              className="uploader__remove"
              aria-label="Remove selected file"
              disabled={disabled}
              onClick={(e) => {
                e.stopPropagation()
                handleRemove()
              }}
            >
              ×
            </button>
          </p>
        )}
      </div>

      {validationError && <p className="uploader__error">{validationError}</p>}

      <button
        type="button"
        className="uploader__submit"
        disabled={!selectedFile || disabled}
        onClick={() => selectedFile && onFileSelected(selectedFile)}
      >
        {disabled ? (
          <>
            <span className="spinner" aria-hidden="true" />
            Parsing…
          </>
        ) : (
          'Parse Report'
        )}
      </button>
    </div>
  )
}
