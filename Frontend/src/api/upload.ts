// src/api/upload.ts

// --- FIX: Define the API_BASE_URL constant directly in this file ---
// This resolves the error because the App component does not export this value.
const API_BASE_URL = 'http://localhost:8000'; // Your FastAPI server URL

/**
 * Uploads a single Job Description file to the backend.
 * @param file The JD file to upload.
 * @returns The parsed JD data from the backend.
 */
export const uploadJdFile = async (file: File) => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE_URL}/upload/jd`, {
    method: 'POST',
    body: formData,
    credentials: 'include', // Required to send the auth cookie
  });

  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || 'Failed to upload JD');
  }

  return response.json();
};

/**
 * Uploads multiple resume files for a specific JD.
 *
 * This function sends the `jdId` in the form data, aligning it
 * with the backend's `/upload/resumes` endpoint.
 *
 * @param files The list of resume files to upload.
 * @param jdId The ID of the job description to associate the resumes with.
 * @returns The result of the upload process from the backend.
 */
export const uploadResumeFiles = async (files: FileList, jdId: string): Promise<{ success: boolean; message: string }> => {
  const formData = new FormData();
  
  formData.append('jd_id', jdId);

  // Append all selected files to the form data under the 'files' key
  for (let i = 0; i < files.length; i++) {
    formData.append('files', files[i]);
  }

  const response = await fetch(`${API_BASE_URL}/upload/resumes`, {
    method: 'POST',
    body: formData,
    credentials: 'include', // Required to send the auth cookie
  });

  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || 'Failed to upload resumes.');
  }

  return response.json();
};