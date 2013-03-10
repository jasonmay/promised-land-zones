#!/usr/bin/env perl
use strict;
use warnings;
use File::Slurp;
use JSON;

my %props;
for my $f (<zones/*.json>) {
    my $contents = read_file($f);
    my $data = JSON::decode_json($contents);
    for my $type (qw/loc obj mob/) {
        while (my ($name, $v) = each $data->{$type}) {
            for my $key (keys %$v) {
                $props{$type}->{$key} = 1;
            }
        }
    }
}

use Data::Dumper::Concise;
print Dumper(\%props);
