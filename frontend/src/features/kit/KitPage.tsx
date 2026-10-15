import { useState, type ReactNode } from 'react';
import { IconBell, IconMap, IconPlus, IconSettings, IconTrash } from '@tabler/icons-react';
import { DateInput } from '@/components/form/DateInput';
import { DateTimeInput } from '@/components/form/DateTimeInput';
import { FileInput } from '@/components/form/FileInput';
import { MultiSelect } from '@/components/form/MultiSelect';
import { NumberInput } from '@/components/form/NumberInput';
import { PasswordInput } from '@/components/form/PasswordInput';
import { SelectInput } from '@/components/form/SelectInput';
import { SwitchInput } from '@/components/form/SwitchInput';
import { TagsInput } from '@/components/form/TagsInput';
import { TextArea } from '@/components/form/TextArea';
import { TextInput } from '@/components/form/TextInput';
import Aurora from '@/components/fx/Aurora';
import BorderGlow from '@/components/fx/BorderGlow';
import CountUp from '@/components/fx/CountUp';
import GlitchText from '@/components/fx/GlitchText';
import { GlowCard } from '@/components/fx/GlowCard';
import { MovingBorder } from '@/components/fx/MovingBorder';
import { Spotlight } from '@/components/fx/Spotlight';
import StarBorder from '@/components/fx/StarBorder';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Combobox, MultiCombobox } from '@/components/ui/combobox';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Field, FieldDescription, FieldLabel } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { Skeleton } from '@/components/ui/skeleton';
import { Slider } from '@/components/ui/slider';
import { Spinner } from '@/components/ui/spinner';
import { Switch } from '@/components/ui/switch';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { confirmAction } from '@/lib/confirm';
import { toast } from '@/lib/toast';

/*
 * Dev-only visual reference of the theme (route /_kit, registered only when import.meta.env.DEV).
 * Every control in its states, a Fatality-like settings panel, the form inputs, overlays and the effects.
 */

const OPTIONS = [
  { value: 'telegram', label: 'Telegram' },
  { value: 'instagram', label: 'Instagram' },
  { value: 'olx', label: 'OLX.kz' },
  { value: 'krisha', label: 'Krisha.kz' },
  { value: 'other', label: 'Other (disabled)', disabled: true },
];

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <div>
        <h2 className="text-xs font-bold tracking-wider text-accent-text uppercase">{title}</h2>
        {hint && <p className="mt-0.5 text-xs text-text-3">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="w-28 shrink-0 text-2xs tracking-wider text-text-3 uppercase">{label}</span>
      {children}
    </div>
  );
}

/** Group box of the Fatality menu: caps header, dense rows "label left, control right". */
function Group({ title, children, className }: { title: string; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded border border-border bg-surface ${className ?? ''}`}>
      <h3 className="border-b border-border px-3 py-1.5 text-2xs font-bold tracking-wider text-text uppercase">{title}</h3>
      <div className="flex flex-col gap-px py-1">{children}</div>
    </section>
  );
}

function Setting({ label, children, disabled }: { label: string; children: ReactNode; disabled?: boolean }) {
  return (
    <div className="flex min-h-7 items-center justify-between gap-4 px-3">
      <span className={disabled ? 'text-sm text-text-disabled' : 'text-sm text-text-2'}>{label}</span>
      <div className="flex w-44 items-center justify-end gap-2">{children}</div>
    </div>
  );
}

function Swatch({ name, className }: { name: string; className: string }) {
  return (
    <div className="flex flex-col gap-1">
      <div className={`h-8 rounded border border-border-strong ${className}`} />
      <span className="text-3xs text-text-3">{name}</span>
    </div>
  );
}

export function KitPage() {
  const [text, setText] = useState('');
  const [number, setNumber] = useState<number | string>(42);
  const [tags, setTags] = useState<string[]>(['alpha', 'beta']);
  const [file, setFile] = useState<File | null>(null);
  const [date, setDate] = useState<string | null>('2026-10-13');
  const [dateTime, setDateTime] = useState<string | null>(null);
  const [platform, setPlatform] = useState<string | null>('telegram');
  const [platforms, setPlatforms] = useState<string[]>(['telegram', 'olx']);
  const [segment, setSegment] = useState('ru');
  const [volume, setVolume] = useState([62]);
  const [enabled, setEnabled] = useState(true);
  const [countKey, setCountKey] = useState(0);
  const [comboDialogValue, setComboDialogValue] = useState<string | null>(null);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-10 px-6 py-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-bold tracking-wider uppercase">
          <span className="text-text">UI kit </span>
          <span className="text-accent-text">/ Fatality</span>
        </h1>
        <p className="text-sm text-text-2">Dev-only reference: tokens, controls in their states, form inputs, overlays and effects.</p>
      </header>

      <Section title="Tokens" hint="bg-bg, bg-surface, bg-surface-raised, bg-surface-sunken, text-text / text-2 / text-3, border-border / border-strong">
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-6 lg:grid-cols-9">
          <Swatch name="bg" className="bg-bg" />
          <Swatch name="surface" className="bg-surface" />
          <Swatch name="surface-raised" className="bg-surface-raised" />
          <Swatch name="surface-sunken" className="bg-surface-sunken" />
          <Swatch name="primary (accent)" className="bg-primary" />
          <Swatch name="accent-hover" className="bg-accent-hover" />
          <Swatch name="accent-text" className="bg-accent-text" />
          <Swatch name="zone-green" className="bg-zone-green" />
          <Swatch name="zone-yellow" className="bg-zone-yellow" />
          <Swatch name="zone-red" className="bg-zone-red" />
          <Swatch name="zone-none" className="bg-zone-none" />
          <Swatch name="graph-developer" className="bg-graph-developer" />
          <Swatch name="border" className="bg-border" />
          <Swatch name="border-strong" className="bg-border-strong" />
          <Swatch name="text" className="bg-text" />
          <Swatch name="text-2" className="bg-text-2" />
          <Swatch name="text-3" className="bg-text-3" />
          <Swatch name="text-disabled" className="bg-text-disabled" />
        </div>
      </Section>

      <Section title="Buttons">
        <Row label="variants">
          <Button>Default</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="destructive">Destructive</Button>
          <Button variant="link">Link</Button>
        </Row>
        <Row label="sizes">
          <Button size="xs">Extra small</Button>
          <Button size="sm">Small</Button>
          <Button size="md">Medium</Button>
          <Button size="icon" aria-label="Add">
            <IconPlus />
          </Button>
          <Button size="icon-sm" variant="secondary" aria-label="Settings">
            <IconSettings />
          </Button>
          <Button size="icon-xs" variant="ghost" aria-label="Delete">
            <IconTrash />
          </Button>
        </Row>
        <Row label="with icon">
          <Button>
            <IconMap /> Open map
          </Button>
          <Button variant="secondary">
            <IconBell /> Notify
          </Button>
        </Row>
        <Row label="states">
          <Button disabled>Disabled</Button>
          <Button variant="secondary" disabled>
            Disabled
          </Button>
          <Button loading>Loading</Button>
          <Button variant="secondary" loading>
            Loading
          </Button>
        </Row>
      </Section>

      <Section title="Badges and zone chips" hint="Zone tones are for zones only; a zone is always spelled out in words.">
        <Row label="tones">
          <Badge variant="default">Brand</Badge>
          <Badge variant="secondary">Neutral</Badge>
          <Badge variant="outline">Outline</Badge>
          <Badge variant="destructive">Destructive</Badge>
        </Row>
        <Row label="zones">
          <Badge variant="green">Green zone 12</Badge>
          <Badge variant="yellow">Yellow zone 45</Badge>
          <Badge variant="red">Red zone 87</Badge>
          <Badge variant="none">No score</Badge>
        </Row>
        <Row label="zone dots">
          <span className="inline-flex items-center gap-1.5 text-sm text-zone-green-ink">
            <span className="size-2 rounded-full bg-zone-green" /> Green
          </span>
          <span className="inline-flex items-center gap-1.5 text-sm text-zone-yellow-ink">
            <span className="size-2 rounded-full bg-zone-yellow" /> Yellow
          </span>
          <span className="inline-flex items-center gap-1.5 text-sm text-zone-red-ink">
            <span className="size-2 rounded-full bg-zone-red shadow-[0_0_8px_var(--zone-red)]" /> Red
          </span>
          <span className="inline-flex items-center gap-1.5 text-sm text-zone-none-ink">
            <span className="size-2 rounded-full bg-zone-none" /> None
          </span>
        </Row>
      </Section>

      <Section title="Settings panel" hint="Group boxes with 11px caps headers and 28px rows: label left, control right.">
        <div className="grid gap-4 md:grid-cols-2">
          <Group title="Detection">
            <Setting label="Enabled">
              <Switch checked={enabled} onCheckedChange={setEnabled} aria-label="Enabled" />
            </Setting>
            <Setting label="Strict mode">
              <Checkbox defaultChecked aria-label="Strict mode" />
            </Setting>
            <Setting label="Sensitivity">
              <Slider value={volume} onValueChange={setVolume} aria-label="Sensitivity" className="min-w-0 flex-1" />
              <span className="w-9 shrink-0 text-right text-xs text-text-2 tabular-nums">{volume[0]}%</span>
            </Setting>
            <Setting label="Source">
              <Select value={platform ?? undefined} onValueChange={setPlatform}>
                <SelectTrigger aria-label="Source">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value} disabled={option.disabled}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Setting>
            <Setting label="Language">
              <ToggleGroup type="single" value={segment} onValueChange={(next) => next && setSegment(next)} aria-label="Language">
                <ToggleGroupItem value="ru">RU</ToggleGroupItem>
                <ToggleGroupItem value="kk">ҚАЗ</ToggleGroupItem>
              </ToggleGroup>
            </Setting>
            <Setting label="Disabled option" disabled>
              <Switch disabled aria-label="Disabled option" />
            </Setting>
          </Group>
          <Group title="Notifications">
            <Setting label="Threshold">
              <Input defaultValue="70" aria-label="Threshold" />
            </Setting>
            <Setting label="Recipient">
              <Input placeholder="name@domain.kz" aria-label="Recipient" />
            </Setting>
            <Setting label="Bad value">
              <Input defaultValue="oops" aria-invalid aria-label="Bad value" />
            </Setting>
            <Setting label="Locked" disabled>
              <Input defaultValue="read only" disabled aria-label="Locked" />
            </Setting>
            <Setting label="Apply">
              <Button size="sm">Save</Button>
              <Button size="sm" variant="secondary">
                Reset
              </Button>
            </Setting>
          </Group>
        </div>
      </Section>

      <Section title="Primitives (ui)">
        <div className="grid gap-4 md:grid-cols-3">
          <Field>
            <FieldLabel htmlFor="kit-input">Input</FieldLabel>
            <Input id="kit-input" placeholder="Placeholder" />
            <FieldDescription>Hint under the control</FieldDescription>
          </Field>
          <Field>
            <Label htmlFor="kit-textarea">Textarea</Label>
            <Textarea id="kit-textarea" placeholder="Grows with its text" />
          </Field>
          <div className="flex flex-col gap-2">
            <Label>Checkbox and switch</Label>
            <div className="flex items-center gap-2 text-sm text-text-2">
              <Checkbox id="kit-c1" /> <Label htmlFor="kit-c1">Unchecked</Label>
            </div>
            <div className="flex items-center gap-2 text-sm text-text-2">
              <Checkbox id="kit-c2" defaultChecked /> <Label htmlFor="kit-c2">Checked</Label>
            </div>
            <div className="flex items-center gap-2 text-sm text-text-2">
              <Checkbox id="kit-c3" disabled /> <Label htmlFor="kit-c3">Disabled</Label>
            </div>
            <div className="flex items-center gap-2 text-sm text-text-2">
              <Checkbox id="kit-c4" aria-invalid /> <Label htmlFor="kit-c4">Invalid</Label>
            </div>
            <div className="flex items-center gap-3">
              <Switch aria-label="Off" />
              <Switch defaultChecked aria-label="On" />
              <Switch disabled aria-label="Disabled off" />
              <Switch disabled defaultChecked aria-label="Disabled on" />
            </div>
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="flex flex-col gap-1">
            <Label>Select</Label>
            <Select defaultValue="olx">
              <SelectTrigger>
                <SelectValue placeholder="Choose" />
              </SelectTrigger>
              <SelectContent>
                {OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value} disabled={option.disabled}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1">
            <Label>Combobox (searchable)</Label>
            <Combobox options={OPTIONS} value={platform} onChange={setPlatform} placeholder="Choose" clearable />
          </div>
          <div className="flex flex-col gap-1">
            <Label>Multi combobox</Label>
            <MultiCombobox options={OPTIONS} value={platforms} onChange={setPlatforms} placeholder="Choose" clearable />
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="flex flex-col gap-2">
            <Label>Toggle group (segmented control)</Label>
            <ToggleGroup type="single" value={segment} onValueChange={(next) => next && setSegment(next)}>
              <ToggleGroupItem value="ru">RU</ToggleGroupItem>
              <ToggleGroupItem value="kk">ҚАЗ</ToggleGroupItem>
              <ToggleGroupItem value="en">EN</ToggleGroupItem>
            </ToggleGroup>
          </div>
          <div className="flex flex-col gap-2">
            <Label>Slider</Label>
            <Slider value={volume} onValueChange={setVolume} />
            <Slider defaultValue={[20, 70]} />
            <Slider defaultValue={[40]} disabled />
          </div>
          <div className="flex flex-col gap-2">
            <Label>Avatar, spinner, skeleton</Label>
            <div className="flex items-center gap-3">
              <Avatar>
                <AvatarFallback>MI</AvatarFallback>
              </Avatar>
              <Avatar size="sm">
                <AvatarFallback>GA</AvatarFallback>
              </Avatar>
              <Spinner />
              <Skeleton className="h-4 w-32" />
            </div>
          </div>
        </div>
        <Tabs defaultValue="map">
          <TabsList>
            <TabsTrigger value="map">
              <IconMap /> Map
            </TabsTrigger>
            <TabsTrigger value="objects">Objects</TabsTrigger>
            <TabsTrigger value="signals">Signals</TabsTrigger>
            <TabsTrigger value="admin" disabled>
              Admin
            </TabsTrigger>
          </TabsList>
          <TabsContent value="map" className="text-sm text-text-2">
            Inactive tabs are text-3, the active one is pink with an underline.
          </TabsContent>
          <TabsContent value="objects" className="text-sm text-text-2">
            Objects tab content.
          </TabsContent>
          <TabsContent value="signals" className="text-sm text-text-2">
            Signals tab content.
          </TabsContent>
        </Tabs>
        <Separator />
        <div className="rounded border border-border bg-surface">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Code</TableHead>
                <TableHead>Object</TableHead>
                <TableHead>Zone</TableHead>
                <TableHead className="text-right">Score</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell className="text-text-3">OBJ-001</TableCell>
                <TableCell>ЖК «Золотая осень»</TableCell>
                <TableCell>
                  <Badge variant="red">Red zone</Badge>
                </TableCell>
                <TableCell className="text-right tabular-nums">87</TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="text-text-3">OBJ-002</TableCell>
                <TableCell>ЖК «Берёзовая роща»</TableCell>
                <TableCell>
                  <Badge variant="yellow">Yellow zone</Badge>
                </TableCell>
                <TableCell className="text-right tabular-nums">45</TableCell>
              </TableRow>
              <TableRow data-state="selected">
                <TableCell className="text-text-3">OBJ-003</TableCell>
                <TableCell>ЖК «Радужный парк» (selected)</TableCell>
                <TableCell>
                  <Badge variant="green">Green zone</Badge>
                </TableCell>
                <TableCell className="text-right tabular-nums">12</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </Section>

      <Section title="Form inputs (components/form)" hint="Label, hint and error in one wrapper; the error state is red. Names and value types follow the Mantine inputs.">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          <TextInput label="TextInput" description="A hint under the label" placeholder="Type here" value={text} onChange={(event) => setText(event.target.value)} />
          <TextInput label="Required" required placeholder="Required field" />
          <TextInput label="With error" defaultValue="wrong" error="Something is wrong with this value" />
          <TextInput label="Disabled" disabled defaultValue="disabled" />
          <PasswordInput label="PasswordInput" defaultValue="secret" />
          <NumberInput label="NumberInput" description="min 0, max 100, step 5" value={number} onChange={setNumber} min={0} max={100} step={5} />
          <NumberInput label="No controls, 6 decimals" value={51.1282} onChange={() => undefined} decimalScale={6} hideControls />
          <TextArea label="TextArea" minRows={2} maxRows={5} placeholder="Grows up to 5 lines" />
          <TagsInput label="TagsInput" description="Enter or comma adds a tag" value={tags} onChange={setTags} placeholder="Add tag" />
          <FileInput label="FileInput" placeholder="Choose a file" value={file} onChange={setFile} clearable />
          <DateInput label="DateInput" description="Type 13.10.2026 or pick" value={date} onChange={setDate} clearable />
          <DateTimeInput label="DateTimeInput" value={dateTime} onChange={setDateTime} clearable />
          <SelectInput label="SelectInput" data={OPTIONS} value={platform} onChange={setPlatform} clearable placeholder="Choose" />
          <SelectInput label="SelectInput (searchable)" data={OPTIONS} value={platform} onChange={setPlatform} searchable clearable placeholder="Choose" />
          <MultiSelect label="MultiSelect" data={OPTIONS} value={platforms} onChange={setPlatforms} clearable placeholder="Choose" />
          <SelectInput label="Select with error" data={OPTIONS} value={null} onChange={() => undefined} error="Required" placeholder="Choose" />
          <DateInput label="Date with error" value={null} onChange={() => undefined} error="Pick a date" />
          <SwitchInput label="SwitchInput" description="Label and hint beside the switch" checked={enabled} onCheckedChange={setEnabled} />
        </div>
      </Section>

      <Section title="Overlays, toasts, confirm">
        <div className="flex flex-wrap items-center gap-2">
          <Dialog>
            <DialogTrigger asChild>
              <Button variant="secondary">Dialog</Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle>Add publication</DialogTitle>
                <DialogDescription>A window on the raised surface with the pink-tinted window shadow.</DialogDescription>
              </DialogHeader>
              <TextInput label="Title" placeholder="Title" />
              <SelectInput label="Searchable select inside a dialog" searchable clearable data={OPTIONS} value={comboDialogValue} onChange={setComboDialogValue} />
              <DateInput label="Date inside a dialog" value={date} onChange={setDate} />
              <DialogFooter>
                <Button variant="secondary">Cancel</Button>
                <Button>Save</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="secondary">Sheet</Button>
            </SheetTrigger>
            <SheetContent>
              <SheetHeader>
                <SheetTitle>Side panel</SheetTitle>
                <SheetDescription>Replaces the Mantine Drawer.</SheetDescription>
              </SheetHeader>
              <ScrollArea className="min-h-0 flex-1 px-3">
                <p className="text-sm text-text-2">Scrollable content goes here.</p>
              </ScrollArea>
            </SheetContent>
          </Sheet>
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="secondary">Popover</Button>
            </PopoverTrigger>
            <PopoverContent>
              <p className="text-sm text-text-2">Popover content on the raised surface.</p>
            </PopoverContent>
          </Popover>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="secondary">Menu</Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuLabel>Account</DropdownMenuLabel>
              <DropdownMenuItem>Profile</DropdownMenuItem>
              <DropdownMenuItem>Settings</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem variant="destructive">Sign out</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost">Tooltip</Button>
            </TooltipTrigger>
            <TooltipContent>Short hint on the raised surface</TooltipContent>
          </Tooltip>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={() => toast.success('Saved')}>
            toast.success
          </Button>
          <Button variant="outline" onClick={() => toast.error('The server is unreachable', { title: 'Error' })}>
            toast.error
          </Button>
          <Button variant="outline" onClick={() => toast.info('Synchronization started')}>
            toast.info
          </Button>
          <Button
            variant="outline"
            onClick={() =>
              confirmAction({ title: 'Send the card?', message: 'The card goes to the recipient and is locked for editing.', confirmLabel: 'Send', onConfirm: () => toast.success('Sent') })
            }
          >
            confirmAction
          </Button>
          <Button
            variant="outline"
            onClick={() =>
              confirmAction({
                title: 'Delete the phrase?',
                message: 'This cannot be undone.',
                confirmLabel: 'Delete',
                danger: true,
                onConfirm: () => toast.success('Deleted'),
              })
            }
          >
            confirmAction (danger)
          </Button>
        </div>
      </Section>

      <Section title="Effects (components/fx)" hint="All of them stand still under prefers-reduced-motion.">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="flex flex-col gap-1">
            <span className="text-2xs tracking-wider text-text-3 uppercase">GlowCard: move the cursor near the border</span>
            <GlowCard className="p-4">
              <p className="text-sm text-text-2">A panel whose border lights up pink towards the cursor within 80px.</p>
            </GlowCard>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-2xs tracking-wider text-text-3 uppercase">Spotlight</span>
            <div className="relative h-32 overflow-hidden rounded border border-border bg-surface">
              <Spotlight />
              <p className="relative p-4 text-sm text-text-2">A pink light cone from the top, fades in once.</p>
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-2xs tracking-wider text-text-3 uppercase">MovingBorder</span>
            <div>
              <MovingBorder>
                <Button>Confirm and send</Button>
              </MovingBorder>
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-2xs tracking-wider text-text-3 uppercase">StarBorder (island pill)</span>
            <div>
              <StarBorder as="div" radius={999} className="px-4 py-1.5 text-xs" duration={5}>
                Monitoring · 3 new
              </StarBorder>
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-2xs tracking-wider text-text-3 uppercase">GlitchText</span>
            <GlitchText className="text-3xl" backgroundColor="var(--bg)">
              SAQ QURYLYS
            </GlitchText>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-2xs tracking-wider text-text-3 uppercase">CountUp</span>
            <div className="flex items-center gap-3">
              <span className="text-3xl font-bold text-zone-red-ink tabular-nums">
                <CountUp key={countKey} to={1284} duration={1.6} separator=" " />
              </span>
              <Button size="sm" variant="secondary" onClick={() => setCountKey((key) => key + 1)}>
                Replay
              </Button>
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-2xs tracking-wider text-text-3 uppercase">BorderGlow (red zone card)</span>
            <BorderGlow glowColor="5 100 62" colors={['var(--zone-red-ink)', 'var(--accent-text)', 'var(--zone-red)']}>
              <div className="p-4 text-sm text-text-2">Calm at rest; the glow follows the cursor along the border.</div>
            </BorderGlow>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-2xs tracking-wider text-text-3 uppercase">Aurora</span>
            <div className="relative h-40 overflow-hidden rounded border border-border bg-bg">
              <Aurora />
            </div>
          </div>
        </div>
      </Section>
    </div>
  );
}
