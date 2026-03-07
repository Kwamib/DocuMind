// ============================================================
// DocuMind Chat Component (Enhanced with Document Viewer)
// ============================================================

import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';

// ------------------------------------------------------------
// Interfaces
// ------------------------------------------------------------

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  sources?: any[];
  confidence?: number | null;
  warning?: string | null;
  timestamp: string;
}

interface AskResponse {
  question: string;
  answer: string;
  model: string;
  sources: any[] | null;
  confidence: number | null;
  warning: string | null;
  timestamp: string;
}

interface UploadResponse {
  id: string;
  filename: string;
  pages: number;
  chunks: number;
  timestamp: string;
}

// ------------------------------------------------------------
// Component
// ------------------------------------------------------------

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './chat.component.html',
  styleUrl: './chat.component.css'
})
export class ChatComponent {

  // Chat state
  userInput: string = '';
  messages: ChatMessage[] = [];
  isLoading: boolean = false;
  
  // Document state
  documents: UploadResponse[] = [];
  uploadStatus: string = '';
  
  // NEW: Document viewer state
  // These control what's shown in the document viewer panel
  showViewer: boolean = false;          // Is the viewer panel open?
  viewerDocId: string = '';             // Which document is being viewed
  viewerPageNum: number = 1;            // Which page is displayed
  viewerTotalPages: number = 1;         // Total pages in the document
  viewerFilename: string = '';          // Document name for the header
  viewerImageUrl: string = '';          // URL of the page image
  
  private apiUrl = 'http://localhost:8000';

  constructor(private http: HttpClient) {
    this.loadDocuments();
  }

  loadDocuments(): void {
    this.http.get<UploadResponse[]>(`${this.apiUrl}/api/documents`)
      .subscribe({
        next: (docs) => { this.documents = docs; },
        error: (err) => { console.error('Failed to load documents:', err); }
      });
  }

  onFileSelected(event: any): void {
    const file = event.target.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append('file', file);
    
    this.uploadStatus = `Uploading ${file.name}...`;
    
    this.http.post<UploadResponse>(`${this.apiUrl}/api/upload`, formData)
      .subscribe({
        next: (response) => {
          this.uploadStatus = `Uploaded "${response.filename}" - ${response.pages} pages, ${response.chunks} chunks`;
          this.loadDocuments();
        },
        error: (err) => {
          this.uploadStatus = `Upload failed: ${err.error?.detail || 'Unknown error'}`;
        }
      });
  }

  sendMessage(): void {
    if (!this.userInput.trim() || this.isLoading) return;
    
    const question = this.userInput.trim();
    
    this.messages.push({
      role: 'user',
      content: question,
      timestamp: new Date().toISOString()
    });
    
    this.userInput = '';
    this.isLoading = true;
    
    this.http.post<AskResponse>(`${this.apiUrl}/api/ask`, {
      text: question,
      document_id: null
    }).subscribe({
      next: (response) => {
        this.messages.push({
          role: 'assistant',
          content: response.answer,
          sources: response.sources || undefined,
          confidence: response.confidence,
          warning: response.warning,
          timestamp: response.timestamp
        });
        this.isLoading = false;
      },
      error: (err) => {
        this.messages.push({
          role: 'assistant',
          content: `Error: ${err.error?.detail || 'Failed to get response. Is the backend running?'}`,
          timestamp: new Date().toISOString()
        });
        this.isLoading = false;
      }
    });
  }

  // --------------------------------------------------------
  // NEW: Document Viewer Methods
  // --------------------------------------------------------

  openViewer(docId: string): void {
    /**
     * Open the document viewer for a specific document.
     * 
     * find() searches the documents array for one matching the ID.
     * It's like Python's:
     *   next((d for d in documents if d.id == doc_id), None)
     */
    const doc = this.documents.find(d => d.id === docId);
    if (!doc) return;
    
    this.viewerDocId = docId;
    this.viewerFilename = doc.filename;
    this.viewerTotalPages = doc.pages;
    this.viewerPageNum = 1;
    this.showViewer = true;
    
    // Load the first page image
    this.loadPageImage();
  }

  openViewerFromSource(source: any): void {
    /**
     * Open the viewer to a specific page when user clicks
     * a source citation. This is the "click to see the source" feature.
     * 
     * source.document_id tells us which document
     * source.page tells us which page to jump to
     */
    const doc = this.documents.find(d => d.id === source.document_id);
    if (!doc) return;
    
    this.viewerDocId = source.document_id;
    this.viewerFilename = doc.filename;
    this.viewerTotalPages = doc.pages;
    this.viewerPageNum = source.page;
    this.showViewer = true;
    
    this.loadPageImage();
  }

  closeViewer(): void {
    /** Close the document viewer panel */
    this.showViewer = false;
  }

  loadPageImage(): void {
    /**
     * Build the URL for the page image.
     * 
     * This points to our new /api/documents/{id}/pages/{num} endpoint
     * which converts the PDF page to a PNG image on the fly.
     * 
     * We don't need to make an HTTP call here — we just set the URL
     * and the <img> tag in the HTML loads it automatically.
     * The browser handles the request when it sees the src attribute.
     */
    this.viewerImageUrl = `${this.apiUrl}/api/documents/${this.viewerDocId}/pages/${this.viewerPageNum}`;
  }

  nextPage(): void {
    /** Go to next page if not on the last page */
    if (this.viewerPageNum < this.viewerTotalPages) {
      this.viewerPageNum++;
      this.loadPageImage();
    }
  }

  prevPage(): void {
    /** Go to previous page if not on the first page */
    if (this.viewerPageNum > 1) {
      this.viewerPageNum--;
      this.loadPageImage();
    }
  }

  downloadDocument(docId: string): void {
    /**
     * Download the original PDF.
     * 
     * window.open() opens a URL in a new browser tab.
     * Our /api/documents/{id}/download endpoint returns
     * the actual PDF file, so the browser either displays
     * it or prompts a download.
     */
    window.open(`${this.apiUrl}/api/documents/${docId}/download`, '_blank');
  }
}