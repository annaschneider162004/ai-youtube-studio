def make_srt(text, output_path, seconds_per_line=4):
    lines=[x.strip() for x in text.splitlines() if x.strip()]
    def ts(sec):
        h=sec//3600; m=(sec%3600)//60; s=sec%60
        return f'{h:02d}:{m:02d}:{s:02d},000'
    with open(output_path,'w',encoding='utf-8') as f:
        for i,line in enumerate(lines,1):
            a=(i-1)*seconds_per_line; b=i*seconds_per_line
            f.write(f'{i}\n{ts(a)} --> {ts(b)}\n{line}\n\n')
    return output_path
