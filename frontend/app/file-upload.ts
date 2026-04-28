export type UploadFileCandidate = Pick<File, "name" | "type">;

export const FILE_INPUT_ACCEPT: string | undefined = undefined;
export const SUPPORTED_UPLOAD_EXTENSIONS = [".md", ".json"] as const;

export function isSupportedUploadFile(file: UploadFileCandidate) {
  const filename = file.name.trim().toLowerCase();
  return SUPPORTED_UPLOAD_EXTENSIONS.some((extension) => filename.endsWith(extension));
}

export function partitionSupportedUploadFiles<T extends UploadFileCandidate>(files: readonly T[]) {
  const supportedFiles: T[] = [];
  const rejectedFiles: T[] = [];

  files.forEach((file) => {
    if (isSupportedUploadFile(file)) {
      supportedFiles.push(file);
      return;
    }
    rejectedFiles.push(file);
  });

  return { supportedFiles, rejectedFiles };
}
