<?php
/**
 * Topics list (/{show}/topics/) and single topic (/{show}/topics/{slug}/) - see includes/class-topic-pages.php.
 * Drawn with the theme's header and footer; the look comes from assets/internal-links.css.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$ng_show      = Net_Gain_Topic_Pages::show_slug();
$ng_term      = $ng_show ? get_term_by( 'slug', $ng_show, 'series' ) : null;
$ng_show_name = $ng_term ? $ng_term->name : get_bloginfo( 'name' );
$ng_topic     = Net_Gain_Topic_Pages::current_topic();
$ng_index     = Net_Gain_Entities::index();
$ng_kinds     = Net_Gain_Entities::kinds();
$ng_nbsp12    = 'K&#8209;12';

get_header();
?>

<div class="page-header" style="padding:32px 40px 24px;border-bottom:1px solid var(--bd)">
	<div class="mono" style="font-size:11px;color:var(--mu);letter-spacing:0.12em;text-transform:uppercase"><?php echo esc_html( $ng_show_name ); ?></div>
</div>

<?php if ( function_exists( 'ng_edsby_logo_img' ) ) : ?>
<div class="sponsor-strip" style="border-bottom:1px solid var(--bd);padding:14px 40px;display:flex;align-items:center;justify-content:center;gap:24px;flex-wrap:nowrap">
	<span class="mono" style="font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:var(--mu);white-space:nowrap">Brought to you by</span>
	<div style="width:1px;height:16px;background:var(--bd);flex-shrink:0"></div>
	<a href="https://www.edsby.com/" target="_blank" rel="sponsored noopener"><?php echo ng_edsby_logo_img(); // phpcs:ignore WordPress.Security.EscapeOutput -- built and escaped in the theme ?></a>
	<div style="width:1px;height:16px;background:var(--bd);flex-shrink:0"></div>
	<a href="https://www.edsby.com/" target="_blank" rel="sponsored noopener" class="mono" style="font-size:11px;letter-spacing:0.06em;color:var(--acl);border:1px solid var(--bd);padding:4px 12px">Visit Edsby &rarr;</a>
</div>
<?php endif; ?>

<div class="ng-topics-page">

<?php if ( $ng_topic ) : ?>

	<nav class="mono ng-crumbs" aria-label="Breadcrumb">
		<a href="<?php echo esc_url( home_url( '/' . $ng_show . '/' ) ); ?>"><?php echo esc_html( $ng_show_name ); ?></a> /
		<a href="<?php echo esc_url( Net_Gain_Entities::topics_index_url( $ng_show ) ); ?>">Topics</a> /
		<?php echo esc_html( $ng_topic['name'] ); ?>
	</nav>

	<div class="mono ng-topic-kind"><?php echo esc_html( isset( $ng_kinds[ $ng_topic['kind'] ] ) ? $ng_kinds[ $ng_topic['kind'] ][0] : 'Topic' ); ?></div>
	<h1 class="arch ng-topic-h1"><?php echo esc_html( $ng_topic['name'] ); ?></h1>
	<p class="ng-topic-intro">
		<?php
		printf(
			/* translators: 1 name, 2 count, 3 show, 4 first date, 5 latest date */
			'%1$s has come up in %2$d %3$s newscast%4$s since %5$s; the most recent was on %6$s. Each entry below links to the full newscast, with its transcript and source stories.',
			esc_html( $ng_topic['name'] ),
			(int) $ng_topic['count'],
			esc_html( $ng_show_name ),
			1 === (int) $ng_topic['count'] ? '' : 's',
			esc_html( mysql2date( 'F j, Y', $ng_topic['first'] ) ),
			esc_html( mysql2date( 'F j, Y', $ng_topic['latest'] ) )
		);
		?>
	</p>

	<ol class="ng-timeline">
		<?php foreach ( $ng_topic['episodes'] as $ng_id ) : ?>
			<?php
			if ( ! isset( $ng_index[ $ng_id ] ) ) {
				continue;
			}
			$ng_entry = $ng_index[ $ng_id ];
			$ng_note  = isset( $ng_topic['notes'][ $ng_id ] ) ? $ng_topic['notes'][ $ng_id ] : '';
			?>
			<li>
				<div class="mono ng-timeline-date"><?php echo esc_html( mysql2date( 'M j, Y', $ng_entry['date'] ) ); ?></div>
				<div>
					<a class="arch ng-timeline-title" href="<?php echo esc_url( $ng_entry['url'] ); ?>"><?php echo esc_html( $ng_entry['title'] ); ?></a>
					<?php if ( '' !== $ng_note ) : ?>
						<p class="ng-timeline-note"><?php echo esc_html( $ng_note ); ?></p>
					<?php endif; ?>
					<div class="mono ng-timeline-actions">
						<a href="<?php echo esc_url( add_query_arg( 'autoplay', '1', $ng_entry['url'] ) ); ?>">&#9658; Listen</a>
						<a href="<?php echo esc_url( $ng_entry['url'] . '#transcript' ); ?>">Transcript</a>
					</div>
				</div>
			</li>
		<?php endforeach; ?>
	</ol>

	<?php
	// Topics that appear in the same newscasts (at least two shared), as links to their own pages.
	$ng_together = array();
	foreach ( $ng_topic['episodes'] as $ng_id ) {
		if ( ! isset( $ng_index[ $ng_id ] ) ) {
			continue;
		}
		foreach ( $ng_index[ $ng_id ]['entities'] as $ng_tag ) {
			if ( $ng_tag['slug'] !== $ng_topic['slug'] ) {
				$ng_together[ $ng_tag['slug'] ] = ( $ng_together[ $ng_tag['slug'] ] ?? 0 ) + 1;
			}
		}
	}
	arsort( $ng_together );
	$ng_page_topics = Net_Gain_Entities::page_topics( $ng_show );
	$ng_links       = array();
	foreach ( $ng_together as $ng_slug => $ng_n ) {
		if ( $ng_n >= 2 && isset( $ng_page_topics[ $ng_slug ] ) ) {
			$ng_links[] = $ng_page_topics[ $ng_slug ];
		}
		if ( count( $ng_links ) >= 8 ) {
			break;
		}
	}
	?>
	<?php if ( $ng_links ) : ?>
		<h2 class="arch ng-topics-h2">Often covered together</h2>
		<div class="ng-topic-line">
			<?php foreach ( $ng_links as $ng_other ) : ?>
				<a class="ng-topic" href="<?php echo esc_url( Net_Gain_Entities::topic_url( $ng_show, $ng_other['slug'] ) ); ?>"><?php echo esc_html( $ng_other['name'] ); ?></a>
			<?php endforeach; ?>
		</div>
	<?php endif; ?>

	<p class="mono ng-related-more" style="margin-top:36px">
		<a href="<?php echo esc_url( Net_Gain_Entities::topics_index_url( $ng_show ) ); ?>">&larr; All topics</a>
		<a href="<?php echo esc_url( home_url( '/' . $ng_show . '/episodes/' ) ); ?>">All newscasts &rarr;</a>
	</p>

<?php else : ?>

	<nav class="mono ng-crumbs" aria-label="Breadcrumb">
		<a href="<?php echo esc_url( home_url( '/' . $ng_show . '/' ) ); ?>"><?php echo esc_html( $ng_show_name ); ?></a> / Topics
	</nav>
	<h1 class="arch ng-topic-h1">Topics</h1>
	<?php $ng_page_topics = Net_Gain_Entities::page_topics( $ng_show ); ?>
	<p class="ng-topic-intro">The companies, organizations, places and issues <?php echo esc_html( $ng_show_name ); ?> has covered most often in <?php echo wp_kses( $ng_nbsp12, array() ); ?> education technology, security and policy. Pick one to see every newscast that covered it, with what we reported each time.</p>

	<?php if ( $ng_page_topics ) : ?>
		<div class="ng-topic-groups">
			<?php foreach ( $ng_kinds as $ng_kind => $ng_label ) : ?>
				<?php
				$ng_group = array_filter(
					$ng_page_topics,
					static function ( $t ) use ( $ng_kind ) {
						return $t['kind'] === $ng_kind;
					}
				);
				if ( ! $ng_group ) {
					continue;
				}
				?>
				<section class="ng-topic-group">
					<h2 class="mono"><?php echo esc_html( $ng_label[1] ); ?></h2>
					<ul>
						<?php foreach ( $ng_group as $ng_t ) : ?>
							<li><a href="<?php echo esc_url( Net_Gain_Entities::topic_url( $ng_show, $ng_t['slug'] ) ); ?>"><?php echo esc_html( $ng_t['name'] ); ?></a><span class="mono"><?php echo (int) $ng_t['count']; ?> newscast<?php echo 1 === (int) $ng_t['count'] ? '' : 's'; ?></span></li>
						<?php endforeach; ?>
					</ul>
				</section>
			<?php endforeach; ?>
		</div>
	<?php else : ?>
		<p class="ng-topic-intro">Topics appear here once they have come up in several newscasts.</p>
	<?php endif; ?>

	<p class="mono ng-related-more" style="margin-top:36px"><a href="<?php echo esc_url( home_url( '/' . $ng_show . '/episodes/' ) ); ?>">All newscasts &rarr;</a></p>

<?php endif; ?>

</div>

<?php get_footer(); ?>
