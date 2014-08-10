#!/usr/bin/env perl
use strict;
use warnings;
use File::Slurp;
use JSON;
use GraphViz;

use v5.16;

my %combined;
my %graph;
for my $f (<zones/*.json>) {
    my $contents = read_file($f);
    my $data = JSON::decode_json($contents);
    for my $type (qw/loc obj/) {
        $combined{$type} = {%{$combined{$type} || {}}, %{$data->{$type} || {}}};
    }
}

while (my ($k, $v) = each %{$combined{loc}}) {
    while (my ($dir, $exit) = each %{$v->{exits} || {}}) {
        if ($exit =~ s/^\^//) {
            if (!$combined{obj}{$exit}) {
                warn "MISSING DEST: $k";
                next;
            }
            my $dest_loc = $combined{obj}{$exit}{location};
            $dest_loc =~ s/.+://;

            $combined{loc}{$k}{exits}{$dir} = $dest_loc;
        }
    }
    $graph{$k} = $combined{loc}{$k}{exits};
}

my $count = 1;

my %opp = (
    n => 's',
    s => 'n',
    e => 'w',
    w => 'e',
    u => 'd',
    d => 'u',
);

my %unseen = map {; $_ => 1} keys %graph;
while (scalar keys(%unseen)) {
    my $node = (keys %unseen)[0];

    my $g = GraphViz->new(layout => 'fdp', directed => 0);
    $g->add_node($node, cluster => $count);

    my %subgraph;

    my $recur;
    $recur = sub {
        my ($node, $from) = @_;
        return unless delete($unseen{$node});

        $g->add_edge($from => $node) if $from;

        while (my ($exit, $dest) = each $graph{$node}) {
            next unless length($exit) == 1; # skip diagonals for now
            if (($graph{$dest}{$opp{$exit}}||'') eq $node) {
                no warnings 'recursion';
                $recur->($graph{$node}{$exit}, $node);
            }
        }
    };
    $recur->($node);

    open my $fh, '>', "$count.png";
    binmode $fh;
    print $fh $g->as_png;
    close $fh;
    warn "Wrote to $count.png\n";

    ++$count;
}

