export type UploadFileCandidate = Pick<File, "name" | "type">;

export const FILE_INPUT_ACCEPT: string | undefined = undefined;

export function isMarkdownUploadFile(file: UploadFileCandidate) {
  return file.name.trim().toLowerCase().endsWith(".md");
}

export function partitionMarkdownUploadFiles<T extends UploadFileCandidate>(files: readonly T[]) {
  const markdownFiles: T[] = [];
  const rejectedFiles: T[] = [];

  files.forEach((file) => {
    if (isMarkdownUploadFile(file)) {
      markdownFiles.push(file);
      return;
    }
    rejectedFiles.push(file);
  });

  return { markdownFiles, rejectedFiles };
}
