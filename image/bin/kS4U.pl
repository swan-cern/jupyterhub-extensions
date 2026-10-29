#!/usr/bin/perl -w
#
# obtains and stores kerberos ticket on behalf of user 
# using S4U (Services 4 User) kerberos protocol extensions: 
# http://k5wiki.kerberos.org/wiki/Projects/Services4User
#
# optionally executes a command using acquired kerberos credentials.
#
# S4U2Self - protocol transition
# S4U2Proxy - constrained delegation
#
# this script requires patched version of perl-Authen-Krb5 (1.9)
# and MIT krb5 >= 1.10 (1.8 could work ..)
#
# for S4U to work your Kerberos KDC must be set up in a
# specific way for given principals, see:
#
# http://k5wiki.kerberos.org/wiki/Manual_Testing#Services4User_testing 
#
#
# 2017-03-07 v 0.3 Jakub Moscicki <jakub.moscicki@cern.ch>
#                  - support multiple proxy principals
# 2013-10-14 v 0.2 Jaroslaw Polok <jaroslaw.polok@cern.ch>
#		   - some verbose info
# 2013-10-13 v 0.1 Jaroslaw Polok <jaroslaw.polok@cern.ch>
#                  - initial version

use strict;
use warnings;
# use diagnostics;
use Getopt::Long;
use Pod::Usage;
use Data::Dumper;
use Authen::Krb5;
use File::Temp qw/ tempfile tempdir /;


sub errorout {
    my ($msg,$code)=@_;
    printf("Error: ".$msg."\n");
    exit($code);
}

sub msg {
    my ($msg)= @_;
    printf($msg."\n");
}


#
# do the job
#

my($verbose,$exec,$keytab,$help,$user,$service,$proxy,$ccache);

my %opts=(
	"verbose"	=> \$verbose,
	"execute=s"	=> \$exec,
	"keytab=s"	=> \$keytab,
	"help"		=> \$help,
	"user=s"	=> \$user,
	"service=s"	=> \$service,
	"proxy=s"	=> \$proxy,
	"cache=s"	=> \$ccache,
);

errorout("Invalid options specified.",1) if (GetOptions(%opts) ne 1);

pod2usage(-verbose=> 2) if ($help);

errorout("-k(eytab) option is mandatory, see kS4U --help for help.",1) unless ($keytab);
errorout("Keytab file ($keytab) not readable.",1) if (!-r $keytab);
errorout("-s(ervice) option is mandatory, see kS4U --help for help.",1) unless ($service);
errorout("-u(ser) option is mandatory, see kS4U --help for help.",1) unless ($user);
errorout("At least one of -c(ache) or -e(xecute) must be specified, see kS4U --help for help.",1) if (!$ccache && !$exec); 


my($krb5ccache,$tempccache,$krb5keytab,$krb5princ,$krb5princ_for_user,$krb5princ_for_proxy,
   $krb5creds,@krb5creds_out,$krb5ccache_out,$outccache);

Authen::Krb5::init_context() or errorout(Authen::Krb5::error()." while initializing context.",1);
Authen::Krb5::init_ets() or errorout(Authen::Krb5::error()." while initializing error tables.",1);

(my $FHTEMP,$tempccache) = tempfile( "krb5cc_kS4U_XXXXXX", UNLINK => 1, TMPDIR => 1 );

$krb5ccache = Authen::Krb5::cc_resolve($tempccache) or errorout(Authen::Krb5::error()." while resolving ccache ($tempccache).",1);

$krb5keytab = Authen::Krb5::kt_resolve($keytab) or errorout(Authen::Krb5::error()." while resolving keytab ($keytab).",1);

$krb5princ = Authen::Krb5::parse_name($service) or errorout(Authen::Krb5::error()." while parsing principal ($service).",1);

$krb5ccache->initialize($krb5princ) or errorout(Authen::Krb5::error()." while initalizing ccache.",1);

msg("Authenticating with keytab ($keytab) for principal ($service)") if ($verbose);

$krb5creds = Authen::Krb5::get_init_creds_keytab($krb5princ,$krb5keytab) or errorout(Authen::Krb5::error()." while authenticating with keytab ($keytab) for principal ($service).",1);

$krb5ccache->store_cred($krb5creds) or errorout(Authen::Krb5::error()." while storing credentials in ccache ($tempccache).",1);

$krb5princ_for_user = Authen::Krb5::parse_name($user) or errorout(Authen::Krb5::error()." while parsing for user principal ($user).",1);

if (!$proxy) {

	msg("Acquiring credentials for user ($user) for service ($service) using credentials of principal ($service) [S4U2Self]") if ($verbose);

        my $creds = Authen::Krb5::get_credentials_for_user($krb5princ_for_user, $krb5princ, $krb5ccache) or errorout(Authen::Krb5::error()." while getting credentials for user ($user).",1);
        push @krb5creds_out, $creds

} else {

	foreach my $p (split(',', $proxy)) {
		msg("Acquiring credentials for user ($user) for service ($p) using credentials of principal ($service) [S4U2Proxy]") if ($verbose);

		$krb5princ_for_proxy = Authen::Krb5::parse_name($p) or errorout(Authen::Krb5::error()." while parsing for user principal ($p).",1);
		my $creds = Authen::Krb5::get_credentials_for_proxy($krb5princ_for_user,$krb5princ,$krb5princ_for_proxy,$krb5ccache,$krb5keytab) or errorout(Authen::Krb5::error()." while getting user ($user) credentials for proxy ($p).",1);
		push @krb5creds_out, $creds
	}
}

if($ccache) {
	$outccache=$ccache;
} else {
 	(my $FHTEMP,$outccache) = tempfile( "krb5cc_kS4U_".$user."_XXXXXX",UNLINK => 1, TMPDIR => 1 );
}

$krb5ccache_out = Authen::Krb5::cc_resolve($outccache) or errorout(Authen::Krb5::error()." while resolving ccache ($outccache).",1);

$krb5ccache_out->initialize($krb5princ_for_user) or errorout(Authen::Krb5::error()." while initalizing ccache. ($outccache).",1);

for my $creds (@krb5creds_out) {
	$krb5ccache_out->store_cred($creds) or errorout(Authen::Krb5::error()." while storing user ($user) credentials in ccache ($outccache).",1);
}

if ($ccache) {
	msg("Kerberos ccache for user ($user) for service ($service) [S4U2Self]: ") if (!$proxy && $verbose);
	msg("Kerberos ccache for user ($user) for service ($proxy) [S4U2Proxy]: ") if ($proxy && $verbose);
	msg("KRB5CCNAME=FILE:$outccache");
} 

if ($exec) {
	msg("Executing: KRB5CCNAME=FILE:$outccache $exec") if ($verbose);
	system("KRB5CCNAME=FILE:$outccache $exec");
	if ($? == -1) {
    		errorout("failed to execute: $!",1);
    	}
    	elsif ($? & 127) {
		my $outmsg=
    		errorout("executed command died with signal ".($? & 127).".",1);
	}
}

exit(0);

__END__

=pod

=head1 NAME

kS4U - utility to execute kerberos authenticated command on behalf of user

=head1 DESCRIPTION

kS4U acquires user Kerberos ticket for named service and stores it in a 
dedicated kerberos credentials cache, optionally executing a kerberized
tool using this credentials cache.

Ticket on behalf of user is obtained using Kerberos protocol extensions S4U
('Services 4 User': http://k5wiki.kerberos.org/wiki/Projects/Services4User)

S4U2Self - protocol transition

or

S4U2Proxy - constrained delegation

This tool requires modified version of perl-Authen-Krb5 (1.9)
and MIT krb5 >= 1.10 libraries. (possibly >= 1.8 would work)

=head1 SYNOPSIS

=over 2
	
	kS4U  [--help]

	kS4U --user USER --service SERVICE1 [ --proxy SERVICE2 ]
             --keytab KEYTAB [ --cache CACHE ][ --exec COMMAND ]

=back

=head1 OPTIONS

=over 4

=item B<--help>

Shows this help description

=item B<--user USER> 

Obtain credentials on behalf of USER Kerberos principal (can be specified as USER@REALM).

=item B<--service SERVICE1>

Use this SERVICE1 principal to obtain credentials for user (can be specified as SERVICE1/HOST.DOMAIN[@REALM])

=item B<--proxy SERVICE2,...>

SERVICE1 principal is used to obtain credentials for SERVICE2 for user USER (can be specified as SERVICE2/HOST.DOMAIN[@REALM])

Multiple proxy services may be seperated by commas.

=item B<--keytab KEYTAB>

Kerberos keytab file containing key(s) for SERVICE1.

=item B<--cache /PATH/TO/CACHEFILE>

Kerberos credentials cache file to store user credentials in. If exists it will be overwritten.

=item B<--exec "COMMAND">

Executes named kerberized COMMAND using user credentials stored in Kerberos credentials cache file. 

=item B<--verbose>

Provide more information.

=item B<--debug>

Provide detailed debugging information. 

=back

All options can be abbreviated to shortest distinctive lenght. 
Single minus preceding option name may be used  instead of double one.

=head1 EXIT STATUS

B<0> - Success.

B<1> - An error occured. 

=head1 EXAMPLES

	kS4U --user joeuser --service SERV1/hostname.fully.qualified \
                            --keytab /etc/krb5.keytab.SERV1 \
                            --cache /tmp/krb5ccache_for_joeuser.XXXX
                            
        kS4U --user joeuser --service SERV1/hostname.fully.qualified \
                            --keytab /etc/krb5.keytab.SERV1 \
                            --exec "curl --negotiate -u: https://hostname/kerberos/protected"

	kS4U --user joeuser --service SERV1/hostname.fully.qualified \
                            --keytab /etc/krb5/keytab.SERV1 \
			    --proxy SERV2/hostname2.fully.qualified \
                            --cache /tmp/krb5ccache_for_joeuser.XXXX \
                            --exec "curl --negotiate -u: https://hostname2/krbprotected"                 

	kS4U --user joeuser --service SERV1/hostname.fully.qualified \
                            --keytab /etc/krb5/keytab.SERV1 \
                            --proxy SERV2/hostname2.fully.qualified \
                            --cache /tmp/krb5ccache_for_joeuser.XXXX 
	KRB5CCNAME=FILE:/mp/krb5ccache_for_joeuser.XXXX \
                            curl --negotiate -u: https://hostname2/krbprotected

=head1 AUTHOR

Jaroslaw Polok <Jaroslaw.Polok@cern.ch>

=head1 NOTES

Using Kerberos 'Services 4 User' (S4U) requires specific setup of the Kerberos
KDC for given principals.

In examples above, while using Microsoft Active Directory 2008:

For S4U2Self - protocol transition:

 - SERV1/hostname.fully.qualified principal UserAccountControl attribute
                                  must be set 'TRUSTED_FOR_DELEGATION'

For S4U2Proxy - constrained delegation:

 - SERV1/hostname.fully.qualified principal UserAccountControl must be 
                                  set 'TRUSTED_TO_AUTH_FOR_DELEGATION' 
                                  and its 'msDS-AllowedToDelegateTo' 
                                  attribute must be set to 
                                  SERV2/hostname.fully.qualified

See: http://support.microsoft.com/kb/305144

B<WARNING>: Always store resulting credentials cache file in a safe location: 
            it can be used by anybody to authenticate to SERV1 / SERV2  as 
            USER !

=head1 KNOWN BUGS

Kerberos keytab validity is not checked.

Probably more ....

