export function UserMessage({ text }: { text: string }) {
  return (
    <div className="flex animate-fade-up justify-end">
      <div className="max-w-[85%] rounded-2xl rounded-br-md border border-primary/20 bg-primary/12 px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-line sm:max-w-[75%]">
        <span className="sr-only">You asked: </span>
        {text}
      </div>
    </div>
  );
}
