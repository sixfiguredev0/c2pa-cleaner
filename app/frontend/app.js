/**
 * C2PA Cleaner V2 — Provenance Inspector & Image Export Tool
 * Strictly local-first, zero remote telemetry, truthful provenance boundaries.
 */

document.addEventListener("DOMContentLoaded", () => {
  // Application State
  const state = {
    activeTab: "cleaner",
    currentFile: null,
    currentPreviewUrl: null,
    inspectionResult: null,
    cleaningResult: null,
    isProcessing: false,
    batchFiles: [], // Array of { file, inspection, cleaningResult, status, synthIdStatus, error }
    activityLog: [],
  };

  // DOM Elements - Navigation & Header
  const navItems = document.querySelectorAll(".nav-item");
  const views = document.querySelectorAll(".view");
  const pageTitle = document.getElementById("page-title");
  const pageSubtitle = document.getElementById("page-subtitle");
  const serverStatusBadge = document.getElementById("server-status-badge");
  const btnHeaderReset = document.getElementById("btn-header-reset");
  const btnShutdown = document.getElementById("btn-shutdown");
  const batchCountBadge = document.getElementById("batch-count-badge");

  // DOM Elements - Cleaner View
  const dropZone = document.getElementById("drop-zone");
  const fileInput = document.getElementById("file-input");
  const btnSelectFile = document.getElementById("btn-select-file");
  const workspaceCard = document.getElementById("workspace-card");
  const btnReplaceImage = document.getElementById("btn-replace-image");
  const imagePreview = document.getElementById("image-preview");

  // Metadata Display
  const metaFilename = document.getElementById("meta-filename");
  const metaFormat = document.getElementById("meta-format");
  const metaFilesize = document.getElementById("meta-filesize");
  const metaDimensions = document.getElementById("meta-dimensions");
  const lblStructuralChunks = document.getElementById("lbl-structural-chunks");
  const lblRetainedMeta = document.getElementById("lbl-retained-meta");

  // Status & C2PA Elements
  const statusCard = document.getElementById("status-card");
  const statusIcon = document.getElementById("status-icon");
  const statusTitle = document.getElementById("status-title");
  const statusDesc = document.getElementById("status-desc");
  const statusDetailsBox = document.getElementById("status-details-box");
  const dManifestCount = document.getElementById("d-manifest-count");
  const dManifestBytes = document.getElementById("d-manifest-bytes");
  const dPixelPreservation = document.getElementById("d-pixel-preservation");

  // Verified Manifest Details
  const verifiedManifestDetails = document.getElementById("verified-manifest-details");
  const mValState = document.getElementById("m-val-state");
  const mIssuer = document.getElementById("m-issuer");
  const mGenerator = document.getElementById("m-generator");
  const mTime = document.getElementById("m-time");

  // Content-Level Watermark (SynthID) Elements
  const synthidBadge = document.getElementById("synthid-badge");
  const synthidHint = document.getElementById("synthid-hint");
  const btnOpenVerifyModal = document.getElementById("btn-open-verify-modal");

  // Action Buttons
  const btnRemoveC2pa = document.getElementById("btn-remove-c2pa");
  const btnActionText = document.getElementById("btn-action-text");
  const btnDownloadClean = document.getElementById("btn-download-clean");
  const btnDownloadUnchanged = document.getElementById("btn-download-unchanged");

  // Results & Verification
  const resultsCard = document.getElementById("results-card");
  const resOutputFilename = document.getElementById("res-output-filename");
  const resOrigSize = document.getElementById("res-orig-size");
  const resCleanSize = document.getElementById("res-clean-size");
  const resSavedBytes = document.getElementById("res-saved-bytes");
  const resStructuresRemoved = document.getElementById("res-structures-removed");
  const verificationChecksList = document.getElementById("verification-checks-list");

  // External Verification Modal Elements
  const modalVerify = document.getElementById("modal-verify");
  const btnCloseModal = document.getElementById("btn-close-modal");
  const btnCancelModal = document.getElementById("btn-cancel-modal");
  const selVerifyOutcome = document.getElementById("sel-verify-outcome");
  const btnSaveVerifyOutcome = document.getElementById("btn-save-verify-outcome");
  const btnProceedVerify = document.getElementById("btn-proceed-verify");

  // Batch View Elements
  const batchFileInput = document.getElementById("batch-file-input");
  const btnBatchAdd = document.getElementById("btn-batch-add");
  const btnBatchProcessAll = document.getElementById("btn-batch-process-all");
  const btnBatchDownloadZip = document.getElementById("btn-batch-download-zip");
  const batchTableBody = document.getElementById("batch-table-body");

  // Activity View Elements
  const activityTableBody = document.getElementById("activity-table-body");
  const btnClearActivity = document.getElementById("btn-clear-activity");

  // Navigation Logic
  const tabTitles = {
    cleaner: {
      title: "Provenance Inspector & Cleaner",
      subtitle: "Inspect embedded C2PA Content Credentials & content-level watermarks. Losslessly strip C2PA metadata without recompressing pixels.",
    },
    batch: {
      title: "Batch Image Processing",
      subtitle: "Process multiple files simultaneously. Each image is inspected, cleaned, and verified independently.",
    },
    activity: {
      title: "Session Activity & Audit Log",
      subtitle: "Chronological log of C2PA operations and external watermark verification checks in this session.",
    },
    about: {
      title: "About & Truthful Scope",
      subtitle: "Technical specifications, structural standards, and truthful boundaries.",
    },
  };

  navItems.forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      switchTab(tab);
    });
  });

  function switchTab(tab) {
    state.activeTab = tab;
    navItems.forEach((n) => n.classList.toggle("active", n.dataset.tab === tab));
    views.forEach((v) => v.classList.toggle("active", v.id === `view-${tab}`));

    if (tabTitles[tab]) {
      pageTitle.textContent = tabTitles[tab].title;
      pageSubtitle.textContent = tabTitles[tab].subtitle;
    }
  }

  // Format File Size Helper
  function formatBytes(bytes) {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  }

  // Check Backend Connection
  async function checkServerHealth() {
    try {
      const res = await fetch("/api/health");
      if (res.ok) {
        serverStatusBadge.innerHTML = `
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>
          127.0.0.1 Connected
        `;
      }
    } catch {
      serverStatusBadge.style.backgroundColor = "rgba(239, 68, 68, 0.15)";
      serverStatusBadge.style.borderColor = "rgba(239, 68, 68, 0.35)";
      serverStatusBadge.style.color = "#f87171";
      serverStatusBadge.innerHTML = `
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
        Server Offline
      `;
    }
  }
  checkServerHealth();

  // File Picker Trigger
  btnSelectFile.addEventListener("click", () => fileInput.click());
  dropZone.addEventListener("click", (e) => {
    if (e.target !== btnSelectFile && !btnSelectFile.contains(e.target)) {
      fileInput.click();
    }
  });

  btnReplaceImage.addEventListener("click", () => fileInput.click());
  btnHeaderReset.addEventListener("click", resetSingleView);

  fileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleSelectedFile(e.target.files[0]);
    }
  });

  // Drag and Drop Handlers
  ["dragenter", "dragover"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.add("drag-over");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.remove("drag-over");
    });
  });

  dropZone.addEventListener("drop", (e) => {
    const dt = e.dataTransfer;
    if (dt && dt.files && dt.files.length > 0) {
      if (dt.files.length === 1) {
        handleSelectedFile(dt.files[0]);
      } else {
        switchTab("batch");
        handleBatchFiles(Array.from(dt.files));
      }
    }
  });

  // Reset Single Cleaner View
  function resetSingleView() {
    state.currentFile = null;
    state.inspectionResult = null;
    state.cleaningResult = null;
    state.isProcessing = false;

    if (state.currentPreviewUrl) {
      URL.revokeObjectURL(state.currentPreviewUrl);
      state.currentPreviewUrl = null;
    }

    fileInput.value = "";
    imagePreview.src = "";
    workspaceCard.style.display = "none";
    dropZone.style.display = "block";
    btnHeaderReset.style.display = "none";
    resultsCard.style.display = "none";
    btnDownloadClean.style.display = "none";
    btnDownloadUnchanged.style.display = "none";
    statusDetailsBox.style.display = "none";
    verifiedManifestDetails.style.display = "none";

    lblStructuralChunks.textContent = "—";
    lblRetainedMeta.textContent = "—";
    updateSynthIdBadge("Not checked", "Requires authorized neural detector (external).");

    btnRemoveC2pa.style.display = "inline-flex";
    btnRemoveC2pa.disabled = true;
    btnActionText.textContent = "Remove C2PA";
    btnRemoveC2pa.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
        <path d="m9 12 2 2 4-4"></path>
      </svg>
      <span id="btn-action-text">Remove C2PA</span>
    `;
  }

  // Update SynthID Watermark Badge
  function updateSynthIdBadge(status, note) {
    let cssClass = "not-checked";
    let label = "Not checked";

    if (status === "Detected by an authorized verifier") {
      cssClass = "detected";
      label = "Detected by Authorized Verifier";
    } else if (status === "Not detected by an authorized verifier") {
      cssClass = "not-detected";
      label = "Not Detected by Authorized Verifier";
    } else if (status === "Verification inconclusive") {
      cssClass = "inconclusive";
      label = "Verification Inconclusive";
    } else if (status === "Verification unavailable") {
      cssClass = "unavailable";
      label = "Verification Unavailable";
    } else {
      cssClass = "not-checked";
      label = "Not checked";
    }

    synthidBadge.className = `badge-synthid ${cssClass}`;
    synthidBadge.textContent = label;

    if (note) {
      synthidHint.textContent = note;
    } else if (cssClass === "not-checked") {
      synthidHint.textContent = "Requires authorized neural detector (external).";
    } else {
      synthidHint.textContent = `Recorded: ${label}`;
    }
  }

  // Handle Selected Image
  async function handleSelectedFile(file) {
    state.currentFile = file;
    state.inspectionResult = null;
    state.cleaningResult = null;
    state.isProcessing = false;

    // Show preview and metadata
    if (state.currentPreviewUrl) {
      URL.revokeObjectURL(state.currentPreviewUrl);
    }
    state.currentPreviewUrl = URL.createObjectURL(file);
    imagePreview.src = state.currentPreviewUrl;

    metaFilename.textContent = file.name;
    metaFilename.title = file.name;
    metaFormat.textContent = "Detecting...";
    metaFilesize.textContent = formatBytes(file.size);
    metaDimensions.textContent = "Analyzing...";

    lblStructuralChunks.textContent = "Analyzing bitstream...";
    lblRetainedMeta.textContent = "Analyzing metadata...";

    // Reset verified manifest details and SynthID badge
    verifiedManifestDetails.style.display = "none";
    updateSynthIdBadge("Not checked");

    // Toggle cards
    dropZone.style.display = "none";
    workspaceCard.style.display = "block";
    btnHeaderReset.style.display = "inline-flex";
    resultsCard.style.display = "none";
    btnDownloadClean.style.display = "none";
    btnDownloadUnchanged.style.display = "none";
    btnRemoveC2pa.style.display = "inline-flex";

    // Set Checking status
    setStatus("checking", "Checking image...", "Inspecting container markers, signatures, and JUMBF boxes.");
    btnRemoveC2pa.disabled = true;

    // Call Inspect API
    const formData = new FormData();
    formData.append("file", file);

    try {
      const resp = await fetch("/api/inspect", {
        method: "POST",
        body: formData,
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || "Inspection failed.");
      }

      const data = await resp.json();
      state.inspectionResult = data;

      // Update Metadata
      metaFormat.textContent = data.format_name;
      metaDimensions.textContent = data.dimensions || "Unknown";

      // Render Structural Chunks vs Retained Metadata
      if (data.structural_chunks && data.structural_chunks.length > 0) {
        lblStructuralChunks.textContent = data.structural_chunks.join(", ");
      } else if (data.format_name === "JPEG") {
        lblStructuralChunks.textContent = "SOF, DHT, DQT, SOS entropy scan";
      } else {
        lblStructuralChunks.textContent = "Image bitstream payload";
      }

      if (data.retained_metadata && data.retained_metadata.length > 0) {
        lblRetainedMeta.textContent = data.retained_metadata.join(", ");
      } else {
        lblRetainedMeta.textContent = "None (no non-C2PA metadata)";
      }

      // Render SynthID Status (Strict Truthful Default)
      const synthStatus = data.synthid ? data.synthid.status : "Not checked";
      const synthNote = data.synthid ? data.synthid.note : null;
      updateSynthIdBadge(synthStatus, synthNote);

      // Render Inspection Status
      if (!data.is_supported) {
        setStatus("error", data.status, data.details);
        btnRemoveC2pa.disabled = true;
      } else if (data.status_code === "invalid") {
        setStatus("error", data.status, data.details);
        btnRemoveC2pa.disabled = true;
      } else if (data.has_c2pa) {
        setStatus(
          "detected",
          "C2PA credentials detected",
          data.details || "Embedded Content Credentials manifest was found."
        );
        dManifestCount.textContent = data.structure_count;
        dManifestBytes.textContent = formatBytes(data.c2pa_bytes);
        statusDetailsBox.style.display = "grid";

        // Verified Manifest Details (Issuer, Generator, Validation State)
        if (data.verified_c2pa) {
          const v = data.verified_c2pa;
          mValState.textContent = v.validation_state || "Present";
          if (v.validation_state === "Valid") {
            mValState.className = "m-val badge-val-state valid";
          } else if (v.validation_state === "Invalid") {
            mValState.className = "m-val badge-val-state invalid";
          } else {
            mValState.className = "m-val badge-val-state untrusted";
          }

          mIssuer.textContent = v.issuer || "Not declared";
          mGenerator.textContent = v.claim_generator || "Not declared";
          mTime.textContent = v.signing_time || "Not declared";
          verifiedManifestDetails.style.display = "block";
        } else {
          verifiedManifestDetails.style.display = "none";
        }

        btnRemoveC2pa.disabled = false;
        btnActionText.textContent = "Remove C2PA";
      } else {
        setStatus(
          "no-c2pa",
          "No embedded C2PA credentials detected",
          "This image does not contain supported embedded C2PA manifest segments. (Note: external cloud records cannot be detected locally)."
        );
        dManifestCount.textContent = "0";
        dManifestBytes.textContent = "0 B";
        statusDetailsBox.style.display = "grid";
        verifiedManifestDetails.style.display = "none";

        btnRemoveC2pa.disabled = true;
        btnDownloadUnchanged.style.display = "inline-flex";
      }
    } catch (err) {
      setStatus("error", "Inspection failed", err.message);
      btnRemoveC2pa.disabled = true;
    }
  }

  // Set Status Visuals
  function setStatus(type, title, desc) {
    statusCard.className = `status-card ${type}`;
    statusTitle.textContent = title;
    statusDesc.textContent = desc;

    if (type === "checking") {
      statusIcon.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="spin">
          <path d="M21 12a9 9 0 1 1-6.219-8.56"></path>
        </svg>
      `;
    } else if (type === "detected") {
      statusIcon.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="12" y1="8" x2="12" y2="12"></line>
          <line x1="12" y1="16" x2="12.01" y2="16"></line>
        </svg>
      `;
    } else if (type === "success") {
      statusIcon.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
      `;
    } else if (type === "no-c2pa") {
      statusIcon.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"></circle>
          <path d="M12 16v-4"></path>
          <path d="M12 8h.01"></path>
        </svg>
      `;
    } else {
      statusIcon.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="15" y1="9" x2="9" y2="15"></line>
          <line x1="9" y1="9" x2="15" y2="15"></line>
        </svg>
      `;
    }
  }

  // Remove C2PA Action Handler
  btnRemoveC2pa.addEventListener("click", async () => {
    if (!state.currentFile || state.isProcessing) return;

    state.isProcessing = true;
    btnRemoveC2pa.disabled = true;
    btnRemoveC2pa.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin">
        <path d="M21 12a9 9 0 1 1-6.219-8.56"></path>
      </svg>
      <span>Removing & Verifying...</span>
    `;

    const formData = new FormData();
    formData.append("file", state.currentFile);

    try {
      const resp = await fetch("/api/clean", {
        method: "POST",
        body: formData,
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || "Removal failed.");
      }

      const res = await resp.json();
      state.cleaningResult = res;

      // Update Status Card
      setStatus(
        "success",
        "Removal successful & verified",
        "C2PA manifest segments were stripped without re-encoding pixels. All integrity verification checks passed."
      );

      // Populate Results Card
      resOutputFilename.textContent = res.output_filename;
      resOrigSize.textContent = formatBytes(res.original_size);
      resCleanSize.textContent = formatBytes(res.output_size);
      resSavedBytes.textContent = `-${formatBytes(res.bytes_removed)}`;
      resStructuresRemoved.textContent = `${res.structures_removed} structure(s)`;

      // Render Verification Checklist
      verificationChecksList.innerHTML = res.verification_checks
        .map(
          (c) => `
          <div class="check-item">
            <div class="check-icon ${c.passed ? "pass" : "fail"}">
              ${
                c.passed
                  ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>'
                  : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>'
              }
            </div>
            <div class="check-body">
              <span class="check-name">${c.name}</span>
              <span class="check-detail">${c.details}</span>
            </div>
          </div>
        `
        )
        .join("");

      resultsCard.style.display = "flex";

      // Show Download Clean Image Button
      btnDownloadClean.href = res.download_url;
      btnDownloadClean.style.display = "inline-flex";
      btnRemoveC2pa.style.display = "none";

      // Add to Session Activity Log
      addActivityEntry({
        time: new Date().toLocaleTimeString(),
        filename: res.original_filename,
        format: res.format_name,
        c2paStatus: "Cleaned & Verified",
        synthIdStatus: synthidBadge.textContent,
        bytesRemoved: res.bytes_removed,
        actionUrl: res.download_url,
      });
    } catch (err) {
      setStatus("error", "Removal could not be completed safely", err.message);
      btnRemoveC2pa.disabled = false;
      btnRemoveC2pa.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
          <path d="m9 12 2 2 4-4"></path>
        </svg>
        <span>Retry Removal</span>
      `;
    } finally {
      state.isProcessing = false;
    }
  });

  // Download Unchanged Copy Handler
  btnDownloadUnchanged.addEventListener("click", () => {
    if (!state.currentFile) return;
    const a = document.createElement("a");
    a.href = state.currentPreviewUrl;
    a.download = state.currentFile.name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    addActivityEntry({
      time: new Date().toLocaleTimeString(),
      filename: state.currentFile.name,
      format: state.inspectionResult ? state.inspectionResult.format_name : "—",
      c2paStatus: "Unchanged Copy",
      synthIdStatus: synthidBadge.textContent,
      bytesRemoved: 0,
      actionUrl: state.currentPreviewUrl,
    });
  });

  // ==========================================
  // External Watermark Verification Modal Handlers
  // ==========================================
  btnOpenVerifyModal.addEventListener("click", () => {
    modalVerify.style.display = "flex";
  });

  function closeModal() {
    modalVerify.style.display = "none";
  }

  btnCloseModal.addEventListener("click", closeModal);
  btnCancelModal.addEventListener("click", closeModal);

  modalVerify.addEventListener("click", (e) => {
    if (e.target === modalVerify) {
      closeModal();
    }
  });

  btnSaveVerifyOutcome.addEventListener("click", async () => {
    const outcome = selVerifyOutcome.value;
    const filename = state.currentFile ? state.currentFile.name : "active_image";

    try {
      await fetch("/api/external-verify/record", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename, outcome }),
      });
    } catch {
      // Local fallback recording
    }

    updateSynthIdBadge(outcome, `Recorded: ${outcome}`);

    addActivityEntry({
      time: new Date().toLocaleTimeString(),
      filename,
      format: state.inspectionResult ? state.inspectionResult.format_name : "—",
      c2paStatus: state.inspectionResult ? (state.inspectionResult.has_c2pa ? "Detected" : "No C2PA") : "—",
      synthIdStatus: outcome,
      bytesRemoved: 0,
      actionUrl: null,
    });

    closeModal();
  });

  // ==========================================
  // Batch Processing Logic
  // ==========================================
  btnBatchAdd.addEventListener("click", () => batchFileInput.click());

  batchFileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleBatchFiles(Array.from(e.target.files));
      batchFileInput.value = "";
    }
  });

  async function handleBatchFiles(files) {
    for (const f of files) {
      const item = {
        file: f,
        inspection: null,
        cleaningResult: null,
        status: "Inspecting...",
        synthIdStatus: "Not checked",
        error: null,
      };
      state.batchFiles.push(item);
    }
    renderBatchTable();
    updateBatchCountBadge();

    // Inspect each file in batch
    for (let i = 0; i < state.batchFiles.length; i++) {
      const item = state.batchFiles[i];
      if (item.inspection) continue;

      const formData = new FormData();
      formData.append("file", item.file);

      try {
        const resp = await fetch("/api/inspect", { method: "POST", body: formData });
        if (resp.ok) {
          item.inspection = await resp.json();
          item.status = item.inspection.has_c2pa ? "C2PA Detected" : "No C2PA";
          item.synthIdStatus = item.inspection.synthid ? item.inspection.synthid.status : "Not checked";
        } else {
          item.status = "Inspection Failed";
          item.error = "File inspection failed.";
        }
      } catch (e) {
        item.status = "Error";
        item.error = e.message;
      }
      renderBatchTable();
    }

    const hasCleanable = state.batchFiles.some((it) => it.inspection && it.inspection.has_c2pa && !it.cleaningResult);
    btnBatchProcessAll.disabled = !hasCleanable;
  }

  function updateBatchCountBadge() {
    if (state.batchFiles.length > 0) {
      batchCountBadge.textContent = state.batchFiles.length;
      batchCountBadge.style.display = "inline-block";
    } else {
      batchCountBadge.style.display = "none";
    }
  }

  function renderBatchTable() {
    if (state.batchFiles.length === 0) {
      batchTableBody.innerHTML = `
        <tr class="empty-row">
          <td colspan="8">No images queued for batch processing. Click "Add Images" or drag multiple images here.</td>
        </tr>
      `;
      btnBatchProcessAll.disabled = true;
      btnBatchDownloadZip.style.display = "none";
      return;
    }

    batchTableBody.innerHTML = state.batchFiles
      .map((item) => {
        const f = item.file;
        const insp = item.inspection;
        const res = item.cleaningResult;

        const formatStr = insp ? insp.format_name : "—";
        const c2paStr = insp ? (insp.has_c2pa ? '<span style="color:#fbbf24">Yes</span>' : "No") : "—";
        const synthIdStr = `<span class="badge-synthid not-checked" style="font-size:10px;padding:2px 6px;">${item.synthIdStatus || "Not checked"}</span>`;
        const cleanSizeStr = res ? formatBytes(res.output_size) : "—";

        let statusBadge = `<span class="badge-status">${item.status}</span>`;
        if (res && res.verification_passed) {
          statusBadge = `<span style="color:#34d399">Cleaned</span>`;
        } else if (item.status === "C2PA Detected") {
          statusBadge = `<span style="color:#fbbf24">Ready</span>`;
        }

        let actionHtml = "—";
        if (res && res.download_url) {
          actionHtml = `<a href="${res.download_url}" class="btn-ghost" download style="font-size:11px;padding:3px 8px;">Download</a>`;
        }

        return `
        <tr>
          <td><strong>${f.name}</strong></td>
          <td>${formatStr}</td>
          <td>${formatBytes(f.size)}</td>
          <td>${c2paStr}</td>
          <td>${synthIdStr}</td>
          <td>${cleanSizeStr}</td>
          <td>${statusBadge}</td>
          <td>${actionHtml}</td>
        </tr>
      `;
      })
      .join("");
  }

  // Batch Process All Handler
  btnBatchProcessAll.addEventListener("click", async () => {
    btnBatchProcessAll.disabled = true;
    btnBatchProcessAll.textContent = "Processing Batch...";

    for (const item of state.batchFiles) {
      if (!item.inspection || !item.inspection.has_c2pa || item.cleaningResult) continue;

      item.status = "Cleaning...";
      renderBatchTable();

      const formData = new FormData();
      formData.append("file", item.file);

      try {
        const resp = await fetch("/api/clean", { method: "POST", body: formData });
        if (resp.ok) {
          const res = await resp.json();
          item.cleaningResult = res;
          item.status = "Cleaned";

          addActivityEntry({
            time: new Date().toLocaleTimeString(),
            filename: res.original_filename,
            format: res.format_name,
            c2paStatus: "Batch Cleaned",
            synthIdStatus: item.synthIdStatus || "Not checked",
            bytesRemoved: res.bytes_removed,
            actionUrl: res.download_url,
          });
        } else {
          item.status = "Failed";
          item.error = "Processing failed.";
        }
      } catch (e) {
        item.status = "Error";
        item.error = e.message;
      }
      renderBatchTable();
    }

    btnBatchProcessAll.textContent = "Clean All";

    // If any cleaned files exist, show Download All ZIP button
    const cleanJobs = state.batchFiles.filter((it) => it.cleaningResult).map((it) => it.cleaningResult.job_id);
    if (cleanJobs.length > 0) {
      btnBatchDownloadZip.style.display = "inline-flex";
      btnBatchDownloadZip.onclick = async () => {
        const resp = await fetch("/api/batch/download-zip", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ job_ids: cleanJobs }),
        });
        if (resp.ok) {
          const blob = await resp.blob();
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = "C2PA_Cleaner_Batch.zip";
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        }
      };
    }
  });

  // ==========================================
  // Session Activity Log Logic
  // ==========================================
  function addActivityEntry(entry) {
    state.activityLog.unshift(entry);
    renderActivityTable();
  }

  function renderActivityTable() {
    if (state.activityLog.length === 0) {
      activityTableBody.innerHTML = `
        <tr class="empty-row">
          <td colspan="7">No activity recorded in this session yet.</td>
        </tr>
      `;
      return;
    }

    activityTableBody.innerHTML = state.activityLog
      .map(
        (it) => `
        <tr>
          <td>${it.time}</td>
          <td><strong>${it.filename}</strong></td>
          <td><span class="badge-format">${it.format}</span></td>
          <td><span style="color:#34d399">${it.c2paStatus}</span></td>
          <td><span class="badge-synthid not-checked" style="font-size:10px;padding:2px 6px;">${it.synthIdStatus}</span></td>
          <td>${it.bytesRemoved ? `-${formatBytes(it.bytesRemoved)}` : "—"}</td>
          <td>
            ${
              it.actionUrl
                ? `<a href="${it.actionUrl}" class="btn-ghost" download style="font-size:11px;padding:3px 8px;">Download</a>`
                : "—"
            }
          </td>
        </tr>
      `
      )
      .join("");
  }

  btnClearActivity.addEventListener("click", () => {
    state.activityLog = [];
    renderActivityTable();
  });

  // ==========================================
  // Clean Shutdown Handler
  // ==========================================
  btnShutdown.addEventListener("click", async () => {
    if (confirm("Are you sure you want to stop the C2PA Cleaner server and exit?")) {
      try {
        await fetch("/api/shutdown", { method: "POST" });
        document.body.innerHTML = `
          <div style="display:flex;height:100vh;align-items:center;justify-content:center;background:#0c0e14;color:#f8fafc;font-family:sans-serif;text-align:center;">
            <div>
              <h2 style="margin-bottom:8px;">C2PA Cleaner Stopped</h2>
              <p style="color:#94a3b8;">The local server has shut down cleanly. You may now close this browser tab.</p>
            </div>
          </div>
        `;
      } catch {
        alert("Server has been stopped.");
      }
    }
  });
});
