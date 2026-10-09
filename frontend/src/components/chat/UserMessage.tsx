export function UserMessage({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[88%] whitespace-pre-line rounded-xl rounded-br-[3px] bg-primary px-[15px] py-[11px] text-[14.5px] leading-[1.55] text-white shadow-xs sm:max-w-[620px]">
        <span className="sr-only">You asked: </span>
        {text}
      </div>
    </div>
  );
}
